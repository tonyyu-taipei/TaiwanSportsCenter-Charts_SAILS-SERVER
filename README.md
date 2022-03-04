# 運動中心健身房圖表查詢系統（Sails後端API）

[系統網址](https://tonyyu.taipei/gym-stats)
[Changelog與Known Bugs](https://hackmd.io/@x9VPntxwQemm0h5ceTvAJw/rJrxViL0F)

網站架構含[客戶端](https://github.com/tonyyu-taipei/TaiwanSportsCenter-Charts_CLIENT)、Sails.js後端（此Repo）與[資料庫抓取程式](https://github.com/tonyyu-taipei/TaiwanSportsCenter-Charts_FETCH-SERVER)（共三個程式）

資料庫使用MongoDB

## 用處

提供用戶端抓取資料的API

## 環境設置

請在專案檔根目錄新增.env檔，並在裡面輸入：
```
MONGODB=你的MongoDB連結
```
## API Map
註：以下全部request method皆為GET
1. /data：抓取所有資料庫內資料，以JSON表示，如： 
```json
[
	{
		"time": "2022-01-17T13:09:29.038Z",
		"locationPeople": [
			{
				"short": "BTSC",
				"peoNum": "13",
				"maxPeo": "20"
			},
			{
				"short": "DASC",
				"peoNum": "23",
				"maxPeo": "65"
			},
		],
		"id": "61e56a897c23449eb3acdd9b"
	},
]
```
short為運動中心縮寫、peoNum為當下人數、maxPeo為最多人數

2. /data/date：將抓取所有資料之日期與時間（上方time）
```json
["2022-01-17T13:09:29.038Z","2022-01-17T13:10:28.701Z","2022-01-17T14:32:20.472Z","2022-01-17T14:42:20.534Z","2022-01-17T23:29:20.435Z","2022-01-17T23:49:20.463Z",]
```

3. /data/date?date=***[日期]***

日期格式需JS new Date()可辨識，將回傳符合該日的資料（如1.）。

4. /locations：將抓取所有運動中心名稱（縮寫與中文名）
```json
[
    {"short":"DASC","name":"大安","id":"61e5499321650236cb94f8e9"},
    {"short":"NGSC","name":"南港","id":"61e5499321650236cb94f8ec"},
    {"short":"WSSC","name":"文山","id":"61e5499321650236cb94f8f1"}
]
```


a [Sails v1](https://sailsjs.com) application



### Links

+ [Sails framework documentation](https://sailsjs.com/get-started)
+ [Version notes / upgrading](https://sailsjs.com/documentation/upgrading)
+ [Deployment tips](https://sailsjs.com/documentation/concepts/deployment)
+ [Community support options](https://sailsjs.com/support)
+ [Professional / enterprise options](https://sailsjs.com/enterprise)


### Version info

This app was originally generated on Mon Jan 17 2022 15:08:32 GMT+0800 (台北標準時間) using Sails v1.5.2.

<!-- Internally, Sails used [`sails-generate@2.0.4`](https://github.com/balderdashy/sails-generate/tree/v2.0.4/lib/core-generators/new). -->



<!--
Note:  Generators are usually run using the globally-installed `sails` CLI (command-line interface).  This CLI version is _environment-specific_ rather than app-specific, thus over time, as a project's dependencies are upgraded or the project is worked on by different developers on different computers using different versions of Node.js, the Sails dependency in its package.json file may differ from the globally-installed Sails CLI release it was originally generated with.  (Be sure to always check out the relevant [upgrading guides](https://sailsjs.com/upgrading) before upgrading the version of Sails used by your app.  If you're stuck, [get help here](https://sailsjs.com/support).)
-->

