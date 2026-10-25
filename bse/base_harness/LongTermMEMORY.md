<!-- c3 memory: durable, general domain facts -->
- 北交所新代码段 920xxx（如 920029）。东财行情接口 secid 格式：北交所用 `0.<code>`（如 0.920029）。
- 东财财务数据接口用 SECUCODE，北交所后缀 `.BJ`（如 920029.BJ）。
- 公司全名要区分：920029 = 成都长城开发科技股份有限公司（开发科技）。
- scripts/fetch_bse.py 支持 --quote/--kline/--fin/--ann，全部输出 JSON 到 stdout，无需第三方库。
