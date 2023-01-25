//  Copyright (c) 2023 Fuka Narita.
//  This source code is licensed under the MIT license found in the
//  LICENSE file in the root directory of this source tree.

//  Copyright (c) 2020 Kurohashi-Chu-Murawaki lab, Kyoto University.
//  Licensed under the MIT license.
//  https://opensource.org/licenses/mit-license.php

//
// The code here is loaded after default_chat_prologue.js and 
// before default_chat_epilogue.js
//
console.log('Loading chat.js...');

var isTooShortDialogShown = false;
var isTooLongDialogShown = false;

var chatroomTimestamp = null;

var confirmBeforeStopChat = true;            
var needsLeavingChatroom = true;

// Prevent subsequent polls when the user is leaving.
var isLeaving = false;

var stopChatConfirmed = false;
var events = [];
var pollXhr = null;
var dialog = null;
var waitStartTime = null;
var waitingInterval = null;
var isDialogStarted = false;
var isDialogOver = false;

let disable_tweets = []

function updateProgress(data) {
    var color;
    var progressTitleMsg;
    var msgCountSelf = getMessageCountFor('self');
    var msgCountOther = getMessageCountFor('other');
    if (msgCountSelf < MSG_COUNT_LOW && msgCountOther < MSG_COUNT_LOW) {
        color = 'yellow';
        progressTitleMsg = 'あなたと対話相手の発話を合わせてあと' + (MSG_COUNT_LOW * 2 - msgCountSelf - msgCountOther - 1) + '発話で規定の長さに達します。チャットを続けて下さい。';
    }
    else if (msgCountSelf < MSG_COUNT_HIGH && msgCountOther < MSG_COUNT_HIGH) {
        let end_button = document.getElementById("stop-chat");
        end_button.style.backgroundColor = "#ff322f";
        color = 'green';
        progressTitleMsg = 'チャットが規定の長さになりました。下の「終了」ボタンから対話を終了してください。';
        $('#notification').hide();
        $('#stop-chat').css({visibility: 'visible'});
    }
    else {
        color = 'red';
        progressTitleMsg = 'チャットが長過ぎるようです。チャットを終了して下さい。';
    }
    var width = (msgCountSelf + msgCountOther) / (MSG_COUNT_HIGH * 2);
    width = width * 90;
    $('img#chat-progressbar').attr('src', 'default_static/images/' + color + '.png');
    $('img#chat-progressbar').attr('title', progressTitleMsg);
    $('img#chat-progressbar').attr('width', width + '%');

    $('#chat-progress-text').html('<p class="msg-info">' + progressTitleMsg + '</p>');

}

function getMessageCountFor(user) {
    var n = 0;
    for (var i = 0; i < events.length; i++) {
        if (events[i].type == 'msg' && events[i].from == user)
            n++;
    }
    return n;
}

function updateModel(data) {
    if (!data) {
        console.log('data is null!');
        return;
    }
    chatroomTimestamp = data.modified;
    var latestEvents = data.latestEvents;
    if (!latestEvents) {
        console.log('latestEvents is null!');
        return;
    }
    for (var i = 0, j = 0; i < latestEvents.length; i++) {
        while (j < events.length && events[j].timestamp < latestEvents[i].timestamp) 
            j++;
        if (j < events.length) {
            if (events[j].timestamp == latestEvents[i].timestamp && events[j].from == latestEvents[i].from)
                j++;
            else 
                events.splice(j + 1, 0, latestEvents[i]);
        }
        else
            events.push(latestEvents[i]);
    }
    updateProgress(data);
}

function buildEntry(msg) {
    var msgClass = 'msg ' + (msg.from == 'self' ? 'msg-right' : 'msg-left');
    var user = (msg.from == 'self' ? 'あなた' : '相手');
    var timestamp = new Date(msg.timestamp.substring(0, msg.timestamp.indexOf('.')) + 'Z');
    var time = (timestamp.getHours() < 10 ? '0' + timestamp.getHours() : timestamp.getHours()) + ':' + 
        (timestamp.getMinutes() < 10 ? '0' + timestamp.getMinutes() : timestamp.getMinutes()) + ':' + 
        (timestamp.getSeconds() < 10 ? '0' + timestamp.getSeconds() : timestamp.getSeconds());
    var body = msg.body;
    if (msg.type == 'msg') {
        var reUrl = /(https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*))/g;
        msg.body.replace(reUrl, '<a href="$1" target="_blank">$1</a>');
        body = escapeHtml(body);
        body = body.replace(/\n/g, '<br/>');
    }

    var entry = '<div class="' + msgClass + '">';
    entry += '<div class="msg-avatar"></div>';
    entry += '<div class="msg-bubble msg-type-' + msg.type + '">';
    entry += '<div class="msg-header">';
    entry += '<div class="msg-from">' + msg.from + '</div>';
    entry += '<div class="msg-timestamp">' + msg.timestamp + '</div>';
    entry += '<div class="msg-user">' + user + '</div>';
    entry += '<div class="msg-time">' + time + '</div>';
    entry += '</div>';
    entry += '<div class="msg-body">' + body + '</div>';
    entry += '</div>';
    entry += '</div>';
    return entry; 
}

function updateView() {
    var needsScrolling = false;
    var shownMsgContainer = $('div#messages');
    evtLoop:
    for (var i = 0, j = 0; i < events.length; i++) {
        var evt = events[i];

        while (j < shownMsgContainer.children().length) {
            var child = shownMsgContainer.children().eq(j);
            var timestamp = child.find('.msg-timestamp').text();
            var from = child.find('.msg-from').text();

            j++;
            if (evt.timestamp < timestamp) {
                var entry = buildEntry(evt);
                $(entry).insertBefore(child);
                continue evtLoop;
            }
            else {
                if (evt.timestamp == timestamp)
                    continue evtLoop;
            }
        }
        var entry = buildEntry(evt);
        shownMsgContainer.append(entry);
        needsScrolling = true;
        j++;
    }
    if (needsScrolling)
        $('#messages').prop('scrollTop', 1000000);
    if (events.length > 0 && events[events.length - 1].from != 'self')
        $('#notification').html('<p class="msg-info">あなたから発話してください</p>');
}

function startDialog() {
    if (!isDialogStarted) {
        isDialogStarted = true;
        if (waitingInterval != null) {
            clearInterval(waitingInterval);
            waitingInterval = null;
        }
    }
    $('#message-waiting').hide();
    $('#chatbox-wrapper').show();
    if (isFirstUser) {
        $('#recommender').show();
        $('#first-user-left-panel').show();
        $('#console').show();
        $('#urls').css({visibility: 'visible'});
        $('#notification').html('<p class="msg-info">新聞記事に関する発話で、あなたから対話を始めてください。相手には記事は見えていません。</p>');
    }
    else {
        $('#first-user-left-panel').hide();
        $('#recommended').show();
        $('#urls').css({visibility: 'hidden'});
        $('#notification').html('<p class="msg-info">相手のメッセージをお待ち下さい</p>');
    }
    if (dialog == null)
        $('#new-msg').focus();
}

function stopDialog() {
    $('#notification').css({visibility: 'hidden'});
    $('#controls').hide();
    $('#chatroom-infobox').show();
    $('#first-user-left-panel input').attr('disabled', true);
    $('#notification').hide();
    $('#message-try-later').hide();
    $('#chatbox').removeClass('shadowed');
    var mainBoxHeight = $('#main-box').css('height');
    $('#main-box').css('height', 'calc(' + mainBoxHeight + ' - ' + mainBoxMargin + ')');
    $('#messages').prop('scrollTop', 1000000);
    isDialogOver = true;
}

function pollServer() {
    pollXhr = $.ajax({
        url: "chatroom",
        data: {
            clientTabId: clientTabId,
            id: chatroomId,
            timestamp: chatroomTimestamp,
        },
        timeout: timeoutInMs,
        success: function(result) {
            var data = JSON.parse(result);
            console.dir(data);
            // In the case that the polling request is done just after that the chatroom has been
            // deallocated on the server, the result might be empty so just ignore it.
            if (jQuery.isEmptyObject(data)){
                return;
            }

            // if ('chosenTopic' in data)
            //     $('.topic').text(data['chosenTopic']);

            var needsPolling = true;
            if ('msg' in data && data.msg == "poll expired") {
                // The poll request has expired and has not produced anything.
                // Let's poll again.
                if (!isLeaving)
                    pollServer();
                return;
            }
            else if ('users' in data && data.users.length > 1) {
                if (!isDialogStarted) {
                    startDialog();
                }
            }
            else {
                console.log('data.closed='+data.closed+ ' stopChatConfirmed='+stopChatConfirmed);
                if (data.closed) {
                    isLeaving = true;
                    $('#message-waiting').hide();
                    $('#notification').css({visibility: 'hidden'});
                    $('#controls').hide();
                    $('#chatbox').removeClass('shadowed');
                    var mainBoxHeight = $('#main-box').css('height');
                    $('#main-box').css('height', 'calc(' + mainBoxHeight + ' - ' + mainBoxMargin + ')');
                    if (!stopChatConfirmed) {
                        $('#stop-chat').hide();
                        $('#message-chat-over').show();
                        $('#chatroom-infobox').show();
                        $('#first-user-left-panel input').attr('disabled', true);
                        //if ($('#table-movie-selector').is(':visible'))
                        //    $('#console').hide();
                        $('#notification').hide();
                        $('#messages').prop('scrollTop', 1000000);
                    }
                    // Show the chatbox in the case where the page is reloaded
                    // when the conversation is over.
                    $('#chatbox-wrapper').show();
                    // Leave the chatroom immediately.
                    $.ajax({
                        url: "leave",
                        data: {
                            clientTabId: clientTabId,
                            chatroom: chatroomId,
                            call: 1
                        },
                        success: function(data) {
                            needsPolling = false;
                            if (pollXhr != null) {
                                pollXhr.abort();
                                pollXhr = null;
                            }
                        }
                    });
                }
            }

            updateModel(data);
            updateView();

            if (events.length > 0){
                if (events[events.length - 1].from == 'other' && events[events.length - 1].type == 'msg') {
                    if (isFirstUser) $('#notification').html(
                        '<p class="msg-info">' +
                        '対話中に少なくとも２回「世間のコメント」を利用しながら自然に対話してください。<br>' +
                        '「世間のコメント」を使用するときは、使用するコメントに<img src="static/images/check_mark.png" width="13px">を入れてください。' +
                        '(<span style="font-size:85%">※<img src="static/images/check_mark.png" width="11px">を入れたコメントが自動的に入力されるわけではありません。)</spanstyle>' +
                        '</p>');
                    else $('#notification').html('<p class="msg-info">あなたから発話してください</p>');
                }
            }

            if (!isLeaving) {
                pollServer();
            }
        },
        error: function(xhr, status, msg) {
            console.log('error xhr='+xhr+' status='+status+' msg='+msg + ' isLeaving='+isLeaving);
            if (status == 'timeout' || status == 'error')
                if (!isLeaving)
                    pollServer();
        }
    });
}

function sendMsg() {
    var msg = $('#new-msg').val().trim();
    /*let tweets = document.getElementsByClassName("tweet-check");
    for (var i = 0; i < tweets.length; i++) {
        console.log(tweets[i]);
        //console.log(tweets[i].is(":checked"));
    }*/
    // Ignore empty message.
    if (msg == '')
        return;

    if (
        (events.length == 0 && !isFirstUser)
        || (events.length > 0 && events[events.length - 1].from == 'self' && events[events.length - 1].type == 'msg')) {
        showSimpleDialog('注意', '相手の返信を待ってからメッセージを送信してください。');
        return;
    }

    $('#new-msg').val('');
    if (pollXhr != null) {
        pollXhr.abort();
        pollXhr = null;
    }

    $('#notification').html('<p class="msg-info">相手のメッセージをお待ち下さい</p>');
    let tweet_elements = document.getElementsByClassName('tweet-check');
    var now_tweets = [];

    for (var i = 0; i < tweet_elements.length; i++){
        if (tweet_elements[i].checked && !disable_tweets.includes(i)){
            now_tweets.push(i);
            disable_tweets.push(i)
        }
    }
    now_tweets = now_tweets.toString()

    for (i = 0; i < disable_tweets.length; i++) {
        tweet_elements[disable_tweets[i]].disabled = true;
    }
    $.ajax({
        url: "post",
        data: {
            clientTabId: clientTabId,
            chatroom: chatroomId,
            message: msg,
            tweets: now_tweets
        },
        type: 'POST',
        success: function(result) {
            var data = JSON.parse(result);
            console.dir(data);
            updateModel(data);
            updateView();
            if (events.length > 0){
                if (events[events.length - 1].from == 'self' && events[events.length - 1].type == 'msg') {
                    $('#notification').html('<p class="msg-info">相手のメッセージをお待ち下さい</p>');
                }
            }
            $('#messages').prop('scrollTop', 1000000);
            $('#send').attr('disabled', false);
            if (dialog == null)
                $('#new-msg').attr('disabled', false).focus();
            if (!isTooLongDialogShown && getMessageCountFor('self') >= MSG_COUNT_HIGH && getMessageCountFor('other') >= MSG_COUNT_HIGH) {
                showSimpleDialog('注意', '対話が十分な長さになりました。数回のやり取りで自然な形で対話を終了させて下さい。');
                isTooLongDialogShown = true;
            }
            pollServer();
        }
    });
};

function stopChat() {
    if (!confirmBeforeStopChat) {
        $('#stop-chat').hide();
        $('#message-chat-over').hide();
        if (needsLeavingChatroom) {
            isLeaving = true;
            $.ajax({
                url: "leave",
                data: {
                    clientTabId: clientTabId,
                    chatroom: chatroomId,
                    call: 3
                },
                success: function(result) {
                    if (pollXhr != null) {
                        pollXhr.abort();
                        pollXhr = null;
                    }
                    stopDialog();
                }
            });
            return;
        }
        else {
            if (isDialogStarted) {
                stopDialog();
                return;
            }
        }
    }
    if (isDialogStarted && // 下の||を&&に変更してみた
        (1 && (getMessageCountFor('self') < MSG_COUNT_LOW && getMessageCountFor('other') < MSG_COUNT_LOW))) {
        var msgCountSelf = getMessageCountFor('self');
        var msgCountOther = getMessageCountFor('other');
        let left_length = MSG_COUNT_LOW * 2 - msgCountSelf - msgCountOther - 1
        showSimpleDialog('注意', '規定の長さまであと' + left_length +'発話です。チャットをまだ続けてください。');
        isTooShortDialogShown = true;
        return;
    }
    dialog = $('#dialog-confirm');
    dialog.attr('title', '注意');
    dialog.text('チャットを終了しますか？');
    dialog.dialog({
        resizable: false,
        height: 'auto',
        width: 400,
        modal: true,
        buttons: {
            'はい': function() {
                isLeaving = true;
                $('#message-waiting').hide();
                stopChatConfirmed = true;
                $('#send').attr('disabled', true);
                $('#new-msg').attr('disabled', true);
                $('#send').hide();
                $('#stop-chat').hide();
                $('#message-chat-over').hide();
                dialog.dialog('close');
                dialog = null;
                $.ajax({
                    url: "leave",
                    data: {
                        clientTabId: clientTabId,
                        chatroom: chatroomId,
                        call: 4
                    },
                    success: function(result) {
                        if (pollXhr != null) {
                            pollXhr.abort();
                            pollXhr = null;
                        }
                        $('#controls').hide();
                        if (isDialogStarted) {
                            $('#chatroom-infobox').show();
                            $('#first-user-left-panel input').attr('disabled', true);
                            $('#notification').hide();
                            if ($('#console').is(':visible'))
                                $('#console').hide();
                            $('#chatbox').removeClass('shadowed');
                            var mainBoxHeight = $('#main-box').css('height');
                            $('#main-box').css('height', 'calc(' + mainBoxHeight + ' - ' + mainBoxMargin + ')');
                            $('#messages').prop('scrollTop', 1000000);
                        }
                        else
                            $('#message-thanks').show("slow");
                    }
                });
            },
            'いいえ': function() {
                dialog.dialog('close');
                dialog = null;
                $('#new-msg').focus();
            }
        }
    });
}

function updateWaitingTimer() {
    var now = Date.now();
    var delay = now - waitStartTime;
    if (delay > WAITING_FOR_PARTNER_DELAY) {
        isLeaving = true;
        if (waitingInterval != null) {
            clearInterval(waitingInterval);
            waitingInterval = null;
        }
        $('#message-waiting').hide();
        $('#message-try-later').show("slow");
        $('#stop-chat').hide();
        needsPolling = false;
        if (pollXhr != null) {
            pollXhr.abort();
            pollXhr = null;
        }
        confirmBeforeStopChat = false;
        // Leave the chatroom immediately.
        $.ajax({
            url: "leave",
            data: {
                clientTabId: clientTabId,
                chatroom: chatroomId,
                call: 2
            },
            success: function(result) {
                needsLeavingChatroom = false;
            }
        });
    }
    else {
        if (stopChatConfirmed)
            $('#message-waiting').hide();
        else {
            var msg = $('#message-waiting p:first-of-type').text();
            var delayInSecs = Math.round((WAITING_FOR_PARTNER_DELAY - delay)/1000);


            if (delayInSecs < 2400 && !isDialogStarted) {
                $('#show-client-tab-id').text(clientTabId);
                $('#client-id-box').show();
                isLeaving = true;
                if (waitingInterval != null) {
                    clearInterval(waitingInterval);
                    waitingInterval = null;
                }
                $('#message-waiting').hide();
                $('#message-try-later').show("slow");
                $('#stop-chat').hide();
                needsPolling = false;
                if (pollXhr != null) {
                    pollXhr.abort();
                    pollXhr = null;
                }
                confirmBeforeStopChat = false;
                // Leave the chatroom immediately.
                $.ajax({
                    url: "leave",
                    data: {
                        clientTabId: clientTabId,
                        chatroom: chatroomId,
                        call: 2
                    },
                    success: function(result) {
                        needsLeavingChatroom = false;
                    }
                });
            }



            if (msg.indexOf('(') == -1)
                $('#message-waiting p:first-of-type').text(msg + ' (' + (delayInSecs - 2400) + ' s.)');
            else
                $('#message-waiting p:first-of-type').text(msg.replace(/\(.*\)/, '(' + (delayInSecs - 2400) + ' s.)'));

        }
    }
}

window.addEventListener('beforeunload', function (e) {
    e.returnValue = 'リロードしないでください';
});

$(document).ready(function() {
    $('#message-chat-over').hide();
    $('#client-id-box').hide();

    $('.new-msg-field').on('keypress', function(e) {
        if (e.keyCode == 13 && !e.shiftKey) {
            sendMsg();
            return false;
        }
        return true;
    });

    if (WAITING_FOR_PARTNER_DELAY > 0) {
        $('#chatbox-wrapper').hide();
        $('#message-waiting').show();
        waitStartTime = Date.now();
        waitingInterval = setInterval(updateWaitingTimer, 1000);
    }
    else if (!isFirstUser)
        startDialog();

    pollServer();
});

console.log('chat.js loaded.');
