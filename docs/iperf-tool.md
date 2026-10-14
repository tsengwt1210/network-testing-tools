# iPerf3 Testing Center

主要入口：[`tools/iperf/iperf_gui.py`](../tools/iperf/iperf_gui.py)。

## 執行前

Python 部分只使用標準函式庫，但網路量測需另外安裝 iPerf3。在 Windows 可將 `iperf3.exe` 與該版本需要的 DLL 放在 `tools/iperf/`，或把 iPerf3 加入系統 PATH。本專案不附第三方二進位檔。

ESnet 不提供官方二進位套件，Windows 也不屬於 iPerf3 官方支援的平台。選用的 Windows 建置版本須自行驗證；本 GUI 用到 `--forceflush`。參考 [取得 iPerf3](https://software.es.net/iperf/obtaining.html)、[官方 FAQ](https://software.es.net/iperf/faq.html) 及[參數文件](https://software.es.net/iperf/invoking.html)。

可先用該執行檔確認版本：

```powershell
# 若使用同資料夾的 Windows 執行檔
.\tools\iperf\iperf3.exe --version

# 若已加入 PATH
iperf3 --version
```

## 最小示範：本機 Server 與 Client

1. 在專案根目錄執行 `python tools/iperf/iperf_gui.py`。
2. Mode 選 `Server`，Bind IP 填 `127.0.0.1`，Port 使用介面預設 `27008`，按 **START TEST**。
3. Mode 改為 `Client`，Target IP 填 `127.0.0.1`，Port 同為 `27008`；使用 TCP、10 秒、1 條串流，啟動第二個工作。
4. Client 結束後檢查輸出與 log，最後停止 Server。

這是操作示範，量到的是本機回送路徑。進行兩台設備的實際測試時，改填可連線的測試端位址，並確認防火牆、介面與測試條件。

## 參數與工作管理

| 介面項目 | iPerf3 參數 | 用途 |
| --- | --- | --- |
| Server／Client | `-s`／`-c` | 監聽或連到目標端 |
| Bind IP | `-B` | Server 綁定本機位址；空白則使用 iPerf3 預設 |
| Port | `-p` | Server 與 Client 使用相同連接埠 |
| TCP／UDP | 預設／`-u` | 選擇傳輸協定 |
| Duration | `-t` | Client 測試秒數 |
| Parallel | `-P` | 單一 Client 內的平行串流數 |
| Bandwidth | `-b` | 傳送速率參數，例如 `100M` |
| Window Size | `-w` | socket buffer 參數，例如 `64K` |
| Reverse | `-R` | 由 Server 朝 Client 傳送測試資料 |

每個工作有獨立程序、分頁與停止按鈕。GUI 固定使用 `-i 1 --forceflush` 取得每秒報告並讓輸出及時刷新；Server 模式停用 Client 專用欄位。

不同分頁不代表同一個 Server 可同時服務任意多個測試。要啟動多個 Server，請使用不同的監聽位址或連接埠，並依 iPerf3 的實際行為規劃測試。

## log 與驗證範圍

log 儲存於 `tools/iperf/logs/`，記錄啟動時間、模式、完整命令與附時間戳記的輸出。每次工作建立獨立檔案，先寫表頭再啟動程序，避免初始輸出被覆蓋。完成、手動停止及程序錯誤會顯示不同狀態；連接埠限制為 1–65535，測試秒數與平行串流數須為正整數。

log 可能包含實際測試 IP 等資訊；`logs/` 與測試輸出檔名已列入 `.gitignore`。

目前沒有吞吐量解析器、結果圖表、排程器或自動重試機制。離線測試驗證命令與檔案處理，不代表已驗證第三方 iPerf3 建置版本、網路吞吐量或長時間執行的穩定性。

關閉視窗會請求停止工作，尚未實作等待所有程序退出或強制回收的完整流程；需要保留完整結尾時，先停止工作並確認狀態更新，再關閉視窗。Bandwidth／Window 的格式由 iPerf3 檢查。
