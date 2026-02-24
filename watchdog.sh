#!/bin/bash
# HR Bot Watchdog - следит за ботом и перезапускает если упал

BOT_DIR="/home/z/my-project/hr-mistral-bot"
BOT_CMD="/usr/bin/python3 bot.py"
LOG_FILE="$BOT_DIR/bot.log"
CHECK_INTERVAL=30

cd $BOT_DIR

echo "=== $(date) === Watchdog started" >> $LOG_FILE

while true; do
    # Проверяем, работает ли бот
    if ! pgrep -f "python.*bot.py" > /dev/null; then
        echo "=== $(date) === Bot not running, starting..." >> $LOG_FILE
        
        # Запускаем бот
        $BOT_CMD >> $LOG_FILE 2>&1 &
        
        # Ждём немного и проверяем
        sleep 5
        if pgrep -f "python.*bot.py" > /dev/null; then
            echo "=== $(date) === Bot started successfully" >> $LOG_FILE
        else
            echo "=== $(date) === Failed to start bot" >> $LOG_FILE
        fi
    fi
    
    sleep $CHECK_INTERVAL
done
