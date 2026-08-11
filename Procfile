web: gunicorn logica_ipc.wsgi --bind 0.0.0.0:$PORT
release: python manage.py migrate && python manage.py crear_admin_inicial
