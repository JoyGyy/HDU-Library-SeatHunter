# 杭州电子科技大学图书馆抢座脚本

## 脚本介绍

本脚本用于杭电图书馆自习室座位预约，支持自动登录、批量预约、定时预约、自动签到等功能。

**本脚本仅限用于个人图书馆预约座位，请勿恶意囤座位！**

## 在线使用

直接访问：https://hdu-library-seathunter-production.up.railway.app

## 本地部署

```shell
git clone https://github.com/stormmmg/HDU-Library-SeatHunter.git
cd HDU-Library-SeatHunter
pip install -r requirements.txt
uvicorn server.main:app --host 0.0.0.0 --port 8080
```

## Docker 部署

```shell
docker build -t seathunter .
docker run -p 8080:8080 seathunter
```

最后请各位善用脚本，祝愿各位校友前途似锦，终成所愿。
