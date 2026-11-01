"""스마트 주식연구소: 공개 지수의 정규장 시간봉으로 BB(20,2) 신호 계산.
주의: 정규장 기준 4시간 + 남은 구간(2시간30분)의 묶음이며,
거래소별 별도 4시간봉 원시 데이터와 동일하다고 보장하지 않습니다.
"""
import json
import math
from datetime import datetime, time as clocktime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'docs' / 'market.json'
MARKETS = {
    'kr': {'symbol': '^KS11', 'timezone': 'Asia/Seoul', 'open': (9, 0), 'close': (15, 30)},
    'us': {'symbol': '^NDX', 'timezone': 'America/New_York', 'open': (9, 30), 'close': (16, 0)},
}


def compute(market, frame, now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    tz = ZoneInfo(market['timezone'])
    if frame is None or frame.empty or 'Close' not in frame.columns:
        raise ValueError('시세 데이터 없음')
    if frame.index.tz is None:
        raise ValueError('시간대 없는 시세 데이터')
    bars = frame.tz_convert(tz).sort_index()
    # 중복 시간봉은 가장 나중 것을 우선한다.
    bars = bars[~bars.index.duplicated(keep='last')]
    slots = {}
    for stamp, record in bars.iterrows():
        ts = stamp.to_pydatetime()
        session_open = datetime.combine(ts.date(), clocktime(*market['open']), tzinfo=tz)
        session_close = datetime.combine(ts.date(), clocktime(*market['close']), tzinfo=tz)
        if not session_open <= ts < session_close:
            continue
        slot = int((ts-session_open).total_seconds() // 14400)
        start = session_open + timedelta(hours=4*slot)
        end = min(start+timedelta(hours=4), session_close)
        value = float(record['Close'])
        if not math.isfinite(value) or value <= 0:
            continue
        slots.setdefault((ts.date(),slot), {})[ts] = (end, value)
    completed = []
    for key, hourly in slots.items():
        day, slot = key
        session_open = datetime.combine(day, clocktime(*market['open']), tzinfo=tz)
        session_close = datetime.combine(day, clocktime(*market['close']), tzinfo=tz)
        start = session_open + timedelta(hours=4*slot)
        end = min(start+timedelta(hours=4), session_close)
        # 진행 중인 구간 제외. 최신 봉이 끝까지 수집됐는지도 확인한다.
        if now_utc.astimezone(tz) < end + timedelta(minutes=10):
            continue
        expected = []
        t = start
        while t < end:
            expected.append(t)
            t += timedelta(hours=1)
        if not all(t in hourly for t in expected):
            continue
        completed.append((end, hourly[expected[-1]][1]))
    completed.sort(key=lambda row: row[0])
    if len(completed) < 20:
        raise ValueError(f'완료된 구간 부족: {len(completed)}/20')
    last20 = [v for _,v in completed[-20:]]
    mean = sum(last20)/20
    std = math.sqrt(sum((v-mean)**2 for v in last20)/20)
    lower,upper = mean-2*std,mean+2*std
    close=last20[-1]
    status='wait' if std == 0 else ('buy' if close<=lower else 'sell' if close>=upper else 'wait')
    return {'status':status,'bar_close':completed[-1][0].isoformat(),
            'last_price':round(close,3),'lower':round(lower,3),
            'upper':round(upper,3),'bar_count':len(completed)}


def main():
    import yfinance as yf
    now=datetime.now(timezone.utc)
    payload={'generated_at':now.isoformat(),'method':'regular-hours 4h/2.5h session segments; BB(20,2); closed segments', 'markets':{}}
    for key,market in MARKETS.items():
        try:
            frame=yf.Ticker(market['symbol']).history(period='55d',interval='60m',auto_adjust=False,prepost=False,raise_errors=True)
            payload['markets'][key]=compute(market,frame,now)
            print(key,payload['markets'][key]['status'])
        except Exception as exc:
            payload['markets'][key]={'status':'unavailable','error':str(exc)[:200]}
            print(key,'데이터 확인 불가:',exc)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print('저장:', OUT)

if __name__=='__main__':
    main()
