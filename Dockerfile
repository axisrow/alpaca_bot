# Используем официальный образ Python в качестве базового
FROM python:3.10-slim

# Устанавливаем apt-get и cron
RUN apt-get update && apt-get install -y \
    apt-utils \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы requirements.txt в контейнер
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в контейнер
COPY . .

# Создаем crontab файл
RUN echo "0 10 * * 1-5 /usr/local/bin/python /app/main.py >> /var/log/cron.log 2>&1" > /etc/cron.d/trading-cron

# Даем права на выполнение
RUN chmod 0644 /etc/cron.d/trading-cron

# Применяем cron job
RUN crontab /etc/cron.d/trading-cron

# Создаем лог файл
RUN touch /var/log/cron.log

# Запускаем cron в фоновом режиме и основную команду
CMD cron && tail -f /var/log/cron.log