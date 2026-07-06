#!/bin/bash
# 資料搬運 Pipeline
# 功能：掃描 data/raw/ 偵測新年度 CSV → 搬移至 data/processing/ → 呼叫 Python 清理腳本 → 寫入 log

# 取得專案根目錄（腳本所在的上一層）
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

DIR_RAW="$ROOT/data/raw"
DIR_PROCESSING="$ROOT/data/processing"
LOG_FILE="$ROOT/logs/pipeline.log"
CLEANER="$ROOT/src/cleaner.py"

# 時間戳記格式
timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

# 寫入 log 的函式
log() {
    echo "[$(timestamp)] $1" | tee -a "$LOG_FILE"
}

log "===== Pipeline 啟動 ====="

# 掃描 data/raw/ 底下所有符合 daily_YYYY.csv 格式的檔案
FILES=$(find "$DIR_RAW" -maxdepth 1 -name "daily_*.csv" -type f)

# 若沒有偵測到任何新檔案，記錄後結束
if [ -z "$FILES" ]; then
    log "INFO  沒有偵測到新年度 CSV，Pipeline 結束"
    exit 0
fi

# 逐一處理每個年度檔案
for FILE in $FILES; do
    FILENAME=$(basename "$FILE")
    log "INFO  偵測到新檔案：$FILENAME"

    # 搬移至 data/processing/
    mv "$FILE" "$DIR_PROCESSING/$FILENAME"
    if [ $? -ne 0 ]; then
        log "ERROR 搬移失敗：$FILENAME"
        continue
    fi
    log "INFO  搬移完成：$FILENAME → data/processing/"

    # 呼叫 Python 清理腳本，傳入檔案路徑
    python "$CLEANER" "$DIR_PROCESSING/$FILENAME"
    if [ $? -eq 0 ]; then
        log "INFO  清理成功：$FILENAME"
    else
        log "ERROR 清理失敗：$FILENAME，請檢查 cleaner.py"
    fi
done

log "===== Pipeline 結束 ====="
