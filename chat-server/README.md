# 感想付きニュース雑談対話収集システム

### 使用方法
- https://github.com/ku-nlp/ChatCollectionFramework (以下、ChatCollectionFrameWorkと表記）の通り環境構築を行ってください.
- 構築したChatCollectionFrameWork上に以下の操作を行い、使用してください．
1. config.jsonを追加してください.
1. staticディレクトリにchat.js,  system_instruction.js, urls.js, util.js, style.css, images/check_mark.png, images/dialog_example.pngを追加してください.
1. templatesディレクトリにchatroom.html, errorForbiddenAccess.html, errorInvalidAccess.html, system_index.html, user_index.htmlを追加してください.
1. V1.json, V2.jsonを含むused_newsディレクトリを追加してください.
1. serverディレクトリ下のbase.pyを置換して使用してください.
