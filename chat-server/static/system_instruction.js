//  Copyright (c) 2023 Fuka Narita.
//  This source code is licensed under the MIT license found in the
//  LICENSE file in the root directory of this source tree.

$(document).ready(function(){
    const news_title = news_tuple[0]
    let news_url = news_tuple[1]
    news_url = news_url.trim();
    let div_article = document.getElementById('article');
    let a_element = document.createElement('a');
    a_element.setAttribute('href', news_url);
    a_element.setAttribute('target', '_blank');
    a_element.setAttribute('rel', 'noopener noreferrer');
    a_element.textContent = '新聞記事:' + news_title;
    div_article.appendChild(a_element);

    let how_to_chat = document.getElementById('how-to-chat');
    let ul_elem = document.createElement('ul');
    const instructions = [
        "好奇心旺盛な相手と関係を築くことを目標として対話をしてください。",
        "相手のメッセージを受け取ってからなるべく早く返信してください。",
        "「新聞記事に対する世間のコメント」を利用しながら対話をしてください。(<b>対話中に2回は「新聞記事に対する世間のコメント」を利用するようにしてください</b>)",
        "相手との対話が始まってから相手の返信が6分以上ない場合はグーグルフォームの画面に戻り、そこに書かれた指示に従ってください",
        "発話の仕方は<u>下の対話例</u>を参考にしてください。"
    ]
    for (let i=0; i<instructions.length; i++){
        let li = document.createElement('li');
        li.innerHTML = instructions[i];
        ul_elem.appendChild(li);
    }
    how_to_chat.appendChild(ul_elem);
    let dialog_example_img = document.createElement('img');
    dialog_example_img.setAttribute('id', "dialog-example");
    dialog_example_img.setAttribute('src', 'static/images/dialog_example.png');
    how_to_chat.append(dialog_example_img);
    let about_article = document.createTextNode("（この対話は「Apple watchの新作が発売される新聞記事」に関する対話例です）");
    how_to_chat.append(about_article);

    let tweets_elem = document.getElementById('tweets');
    for (let i=0; i<tweets.length; i++){
        let tweet_elem = document.createElement('input');
        tweet_elem.setAttribute('type', 'checkbox');
        tweet_elem.setAttribute('class', 'tweet-check');
        tweet_elem.setAttribute('name', 'tweet');
        tweet_elem.setAttribute('value', 'val');
        tweets_elem.appendChild(tweet_elem);

        let  comment = document.createTextNode(tweets[i][0]);
        tweets_elem.append(comment);
        let br = document.createElement('br');
        tweets_elem.append(br);
    }
});
