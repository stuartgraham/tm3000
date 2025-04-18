FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt && rm requirements.txt
CMD ["python", "-u", "./main.py"]