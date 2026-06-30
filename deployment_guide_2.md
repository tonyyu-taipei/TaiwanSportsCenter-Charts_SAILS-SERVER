# 臺灣運動中心人流預測系統 - 版本更新部署指引 (deployment_guide_2)

此文件說明當您的伺服器上**已成功部署並運行第一版專案時**，如何將系統升級至此新版（包含「健工台北|石牌 FF053」分支以及 dynamic brand grouping 與氣象氣溫整合功能）。

為了避免重複工作，您不需要重新設定 PM2 開機自啟、Apache2 反向代理與基本環境。請依循以下增量更新步驟：

---

## 1. 更新後端 Sails 代碼與 Python 預測模型

### 步驟 1：拉取最新程式碼
在 VM 的 Sails 專案根目錄下執行 Git 拉取（或是覆蓋更動的檔案）：
```bash
cd /path/to/TaiwanSportsCenter-Charts_SAILS-SERVER
git pull
```

### 步驟 2：在虛擬環境中安裝新 Python 依賴套件
此版本引入了 `meteostat` 氣象套件來取得歷史天氣。請啟用現有的虛擬環境（`venv`）並進行安裝：
```bash
# 1. 啟用您的 Python 虛擬環境
source venv/bin/activate

# 2. 僅安裝新增的 meteostat 套件（其他已存在套件不需重裝）
pip install meteostat
```

### 步驟 3：手動測試預測模型管線
執行腳本以驗證新增的地點與 `meteostat` 運作是否正常：
```bash
python Python/train_predict.py
```
*確認輸出中包含：`Successfully loaded weather for 30 centers.` 且最後寫入 MongoDB 成功。*

---

## 2. 資料庫地點資料更新 (Optional)

新版程式已同步支援從資料庫的 `locations` 集合動態載入地點。
* 若您的 MongoDB Atlas 中已經有 `FF053` 的地點數據，則不需任何操作。
* 若需手動同步或重設地點經緯度，可在 Sails 專案目錄下執行：
  ```bash
  mongoimport --uri "mongodb+srv://<username>:<password>@cluster0.xxxxxx.mongodb.net/sports_center" --collection locations --file Python/sports_center.locations.json --jsonArray --mode merge --upsertFields short
  ```

---

## 3. 重啟 Sails 守護服務 (PM2)

當 Sails 後端程式碼以及 Python 腳本更新完成後，請重啟 PM2 服務以載入最新邏輯：
```bash
pm2 restart sports-center-sails
```
*驗證日誌以確保無報錯：*
```bash
pm2 logs sports-center-sails
```

---

## 4. 前端 Vue 用戶端重新打包與部署

由於前端的 UI 菜單、圖表與 brand grouping 有進行程式變動，請重新編譯並覆蓋網頁伺服器（Apache2）中的舊靜態資源：

### 步驟 1：在本地或建置環境打包
於前端 `TW-Sports-ClientNew` 專案目錄下執行：
```bash
npm run build
```

### 步驟 2：部署打包檔案
將打包產生的 `dist/` 資料夾內之所有檔案（`index.html` 以及 `assets/` 目錄），上傳並覆蓋至 Apache 網頁目錄（例如 `/var/www/html/`），即可完成前端升級。
