FROM python:3.11-alpine
WORKDIR /app

# Bước 1: Cài libpq (thư viện runtime cần thiết để chạy Postgres)
RUN apk add --no-cache libpq tzdata

# Bước 2: Copy file requirements vào trước
COPY requirements.txt .

# Bước 3: Gom cài build-deps, pip install và xóa rác vào 1 layer duy nhất
RUN apk add --no-cache --virtual .build-deps postgresql-dev gcc musl-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Bước 4: Copy file code của mày vào sau cùng
COPY source/ .

CMD ["python", "main.py"]