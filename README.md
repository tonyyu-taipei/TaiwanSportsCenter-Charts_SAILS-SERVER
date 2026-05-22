# 健身房圖表查詢系統（Sails後端API）
此為Vibe Coding版本，無嚴謹測試，如要主要版本，請見github master分支。

[系統網址](https://tonyyu.taipei/gym-stats)  
[Changelog與Known Bugs](https://hackmd.io/@x9VPntxwQemm0h5ceTvAJw/rJrxViL0F)

網站架構含[客戶端](https://github.com/tonyyu-taipei/TaiwanSportsCenter-Charts_CLIENT)、Sails.js後端（此Repo）與[資料庫抓取程式](https://github.com/tonyyu-taipei/TaiwanSportsCenter-Charts_FETCH-SERVER)（共三個程式）。

資料庫使用 MongoDB。

## 用處

提供前端用戶端抓取資料的 API 服務。

## 環境設置與運行

1. 請在專案檔根目錄新增 `.env` 檔，並在裡面輸入：
   ```env
   MONGODB=你的MongoDB連結
   ```
2. 啟動伺服器：
   * 本地開發（預設埠號為 `1337`）：`npm run mon` 或 `node app.js`
   * 生產環境：`npm start`

### 系統配置與安全性
* **跨來源資源共享 (CORS)**：已對所有路由啟用 CORS (`allRoutes: true`)，允許前端跨域請求。
* **安全限制**：**僅開放 `GET` 請求**。其餘所有的 `POST`、`PUT`、`PATCH`、`DELETE` 等 RESTful 寫入與修改 API 皆已完全關閉，未定義的請求與非 `GET` 請求將一律回傳 `404 Not Found`。

---

## API 規格說明

所有 API 均只接受 `GET` 請求，格式均為 JSON。

### 1. 歡迎首頁
* **路徑**：`GET /`
* **回傳範例**：
  ```json
  {
    "status": "success",
    "msg": "Hello! To get started, please visit https://github.com/tonyyu-taipei/TaiwanSportsCenter-Charts_SAILS-SERVER",
    "msgCH": "歡迎瀏覽！如需更多資訊，請前往： https://github.com/tonyyu-taipei/TaiwanSportsCenter-Charts_SAILS-SERVER"
  }
  ```

### 2. 獲取所有健身房資料
* **路徑**：`GET /data`
* **說明**：抓取所有資料庫內的歷史紀錄。
* **回傳範例 (Array of Object)**：
  ```json
  [
    {
      "id": "61e56a897c23449eb3acdd9b",
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
        }
      ]
    }
  ]
  ```
  * `time`：資料獲取時間 (ISO 8601 格式)。
  * `locationPeople`：各場館的人數明細。
    * `short`：場館英文縮寫。
    * `peoNum`：當時在場人數。
    * `maxPeo`：場館最大容納人數。

### 3. 獲取所有有資料的日期/時間列表
* **路徑**：`GET /data/date`
* **說明**：回傳資料庫中所有有紀錄的時間點（以台灣時間為準進行排重與分組）。
* **回傳範例 (Array of String)**：
  ```json
  [
    "2022-01-17T13:09:29.038Z",
    "2022-01-17T13:10:28.701Z",
    "2022-01-17T14:32:20.472Z"
  ]
  ```

### 4. 獲取指定日期的健身房資料
* **路徑**：`GET /data/date?date=[日期]`
* **說明**：回傳符合該日期（台灣時間當天）的所有健身房資料，內部透過 MongoDB 聚合查詢。
* **參數**：
  * `date` (Query Parameter)：可被 JavaScript `new Date()` 辨識的日期格式字串（例如 `2022-01-17` 或 `2022/01/17`）。
* **回傳範例**：同 `GET /data` 的格式。

### 5. 獲取指定日期的健身房資料（備用/記憶體過濾版）
* **路徑**：`GET /data/date1?date=[日期]`
* **說明**：功能與 `/data/date` 相同，但為舊版或備用實作（於伺服器記憶體中載入全部資料再以 `date-fns` 的 `isSameDay` 進行過濾）。
* **參數**：同上。
* **回傳範例**：同 `GET /data` 的格式。

### 6. 獲取人流預測資料（或預測日期列表）
* **路徑**：`GET /data/prediction` 或 `GET /data/prediction?date=[日期]`
* **說明**：
  * **當不帶 `date` 參數時**：回傳所有包含預測人流數據的日期列表。
  * **當帶有 `date` 參數時**：回傳該日期（台灣時間當天）的 XGBoost 未來 48 小時預測人流、對應的天氣特徵及預測主導因子的解析數據。
* **參數**：
  * `date` (可選，Query Parameter)：可被 JavaScript `new Date()` 辨識的日期格式字串（例如 `2026-05-23`）。
* **回傳範例（當不帶 `date` 參數時，Array of String）**：
  ```json
  [
    "2026-05-22T16:00:00.000Z",
    "2026-05-23T16:00:00.000Z"
  ]
  ```
* **回傳範例（當帶有 `date` 參數時，Array of Object）**：
  ```json
  [
    {
      "time": "2026-05-23T06:15:00.000Z",
      "locationPeople": [
        {
          "short": "JJSC",
          "peoNum": 12,
          "maxPeo": 100,
          "dominantFactor": "歷史人流慣性 (92.5%)",
          "weather": {
            "temp": 24.5,
            "min_temp": 21.0,
            "max_temp": 28.0,
            "precipitation": 0.5,
            "precipitation_category": "微量降雨"
          },
          "factors": {
            "歷史人流慣性": 92.5,
            "時間與星期": 5.0,
            "場館基本屬性": 1.2,
            "假日與節慶": 0.0,
            "氣溫因素": 1.0,
            "降雨因素": 0.3
          }
        }
      ]
    }
  ]
  ```

### 7. 獲取所有運動中心名稱與縮寫對照
* **路徑**：`GET /locations`
* **說明**：抓取所有運動中心的中文名稱、英文縮寫與 ID 對照表，供前端側邊欄或下拉選單渲染使用。
* **回傳範例 (Array of Object)**：
  ```json
  [
    {
      "id": "61e5499321650236cb94f8e9",
      "short": "DASC",
      "name": "大安"
    },
    {
      "id": "61e5499321650236cb94f8ec",
      "short": "NGSC",
      "name": "南港"
    }
  ]
  ```

---

### Sails v1 專案資訊與相關連結

* [Sails framework documentation](https://sailsjs.com/get-started)
* [Version notes / upgrading](https://sailsjs.com/documentation/upgrading)
* [Deployment tips](https://sailsjs.com/documentation/concepts/deployment)
* [Community support options](https://sailsjs.com/support)
* [Professional / enterprise options](https://sailsjs.com/enterprise)
