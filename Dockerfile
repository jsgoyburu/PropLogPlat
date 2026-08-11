FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN SECRET_KEY=collectstatic-build-key DEBUG=True python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py crear_admin_inicial && gunicorn logica_ipc.wsgi --bind 0.0.0.0:${PORT:-8000} --access-logfile - --error-logfile -"]
