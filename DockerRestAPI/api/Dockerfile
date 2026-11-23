FROM python:3.13-slim
LABEL maintainer="Nigel Epperson"
WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 80
CMD ["python", "api.py"]
