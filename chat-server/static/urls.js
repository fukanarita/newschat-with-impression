//  Copyright (c) 2023 Fuka Narita.
//  This source code is licensed under the MIT license found in the
//  LICENSE file in the root directory of this source tree.

$(document).ready(function(){
    let ids_element = document.getElementById('urls');
    let head = document.createTextNode("tweetID: ");
    ids_element.appendChild(head);
    for (let i=0; i<tweets.length-1; i++){
        let id = document.createTextNode(tweets[i][1] + ', ');
        ids_element.appendChild(id);
    }
    let tid = document.createTextNode(tweets[tweets.length-1][1]);
    ids_element.appendChild(tid);
    let br = document.createElement('br');
    ids_element.appendChild(br);

});