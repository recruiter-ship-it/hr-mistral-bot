#!/bin/bash
# HR Mistral Bot - Auto-restart wrapper

BOT_DIR="/home/z/my-project/hr-mistral-bot"
BOT_SCRIPT="bot.py"
LOG_FILE="$BOT_DIR/bot.log"
PID_FILE="$BOT_DIR/bot.pid"

cd $BOT_DIR

while true; do
    echo "=== $(date) === Starting HR Bot..." >> $LOG_FILE
    
    # Запуск бота
    /usr/bin/python3 $BOT_SCRIPT >> $LOG_FILE 2>&1
    
    # Если бот упал, ждём и перезапускаем
    EXIT_CODE=$?
    echo "=== $(date) === Bot exited with code $EXIT_CODE, restarting in 10s..." >> $LOG_FILE
    sleep 10
done
