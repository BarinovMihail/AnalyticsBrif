# BRIF MTR Comparator

1. Создать БД MySQL:
   `CREATE DATABASE brifdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
2. Заполнить `.env`
3. Установить зависимости:
   `pip install -r requirements.txt`
4. Запустить приложение:
   `uvicorn app.main:app --reload`
5. Открыть:
   `http://localhost:8000` для фронтенда
   `http://localhost:8000/docs` для Swagger
