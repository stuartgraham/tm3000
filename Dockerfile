FROM python:3.13.3
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt && rm requirements.txt
CMD ["python", "-u", "./main.py"]