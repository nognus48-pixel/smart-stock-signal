# -*- coding: utf-8 -*-
"""Korea/US up to 10 picks: regular-session 4h BB(20,2) proximity screen.
Uses the SAME completed-session candle logic as existing update_signals.py.
This is a screening tool, not a buy recommendation. No order placement.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from update_signals import compute, MARKETS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'docs' / 'picks.json'
# 고정 분석 후보군(지수 전체 구성종목 스캔이 아님). 필요하면 여기서 변경.
KR = {
    '005930.KS': ('삼성전자','반도체 업황과 실적 변동'),
    '000660.KS': ('SK하이닉스','메모리 반도체 업황 변동'),
    '035420.KS': ('NAVER','광고·플랫폼 성장률 및 규제'),
    '035720.KS': ('카카오','플랫폼 수익성 및 규제'),
    '005380.KS': ('현대차','글로벌 자동차 수요 및 환율'),
    '000270.KS': ('기아','자동차 판매와 환율 변동'),
    '051910.KS': ('LG화학','화학 업황과 배터리 소재 수요'),
    '006400.KS': ('삼성SDI','전기차 배터리 수요 변동'),
    '068270.KS': ('셀트리온','바이오 제품 매출과 규제 승인'),
    '207940.KS': ('삼성바이오로직스','수주 및 바이오 규제 환경'),
    '105560.KS': ('KB금융','금리·대손충당금 변화'),
    '055550.KS': ('신한지주','금리·신용손실 위험'),
    '086790.KS': ('하나금융지주','대출 건전성 및 금리'),
    '012330.KS': ('현대모비스','자동차 생산량과 공급망'),
    '066570.KS': ('LG전자','가전·전장 수익성 변동'),
    '028260.KS': ('삼성물산','계열사 가치 및 사업 실적 변동'),
    '003670.KS': ('포스코퓨처엠','이차전지 소재 수요·원가'),
    '005490.KS': ('POSCO홀딩스','철강 업황·원자재 가격'),
    '034730.KS': ('SK','지주사 할인·계열사 실적'),
    '017670.KS': ('SK텔레콤','통신 경쟁·규제'),
    '096770.KS': ('SK이노베이션','정유 마진·에너지 가격'),
    '032830.KS': ('삼성생명','금리 및 보험 투자손익'),
    '003550.KS': ('LG','계열사 가치·지주사 할인'),
    '010130.KS': ('고려아연','금속 가격 및 원가'),
    '009150.KS': ('삼성전기','전자부품 수요 변동'),
}
US = {
    'AAPL': ('애플','제품 수요와 서비스 성장 둔화'),
    'MSFT': ('마이크로소프트','AI 투자비용·클라우드 성장 둔화'),
    'NVDA': ('엔비디아','AI 반도체 수요·높은 기대치'),
    'AMZN': ('아마존','소비 경기·클라우드 성장 둔화'),
    'GOOGL': ('알파벳','광고 경기와 규제'),
    'META': ('메타','광고 경기·설비투자 확대'),
    'TSLA': ('테슬라','차량 수요·가격 경쟁'),
    'AVGO': ('브로드컴','반도체 수요·고객 집중'),
    'COST': ('코스트코','소비 경기·높은 가치평가'),
    'NFLX': ('넷플릭스','구독 성장·콘텐츠 비용'),
    'AMD': ('AMD','반도체 경쟁·수요 변동'),
    'ADBE': ('어도비','구독 성장·AI 경쟁'),
    'CSCO': ('시스코','네트워크 장비 투자 사이클'),
    'PEP': ('펩시코','소비수요·원가 상승'),
    'INTC': ('인텔','공정 투자·수익성 개선 불확실성'),
    'QCOM': ('퀄컴','휴대폰·반도체 수요 변동'),
    'AMGN': ('암젠','신약 임상·규제 위험'),
    'TXN': ('텍사스 인스트루먼트','산업용 반도체 경기'),
    'AMAT': ('어플라이드 머티어리얼즈','반도체 설비투자 변동'),
    'BKNG': ('부킹홀딩스','여행 수요·경기 둔화'),
    'SBUX': ('스타벅스','매장 방문·원가 상승'),
    'INTU': ('인튜이트','중소기업 경기·경쟁'),
    'ISRG': ('인튜이티브서지컬','의료기기 규제·밸류에이션'),
    'LRCX': ('램리서치','반도체 설비투자 사이클'),
    'MU': ('마이크론','메모리 반도체 가격 변동'),
}


def score_frame(frame, market, now):
    result = compute(market, frame, now)
    close, lower, upper = (float(result[k]) for k in ('last_price','lower','upper'))
    if lower <= 0 or close <= 0 or not all(math.isfinite(x) for x in (close,lower,upper)):
        raise ValueError('가격/하단 밴드 비정상')
    # 마감된 마지막 구간이 너무 오래되면 추천 후보 제외
    close_utc = datetime.fromisoformat(result['bar_close']).astimezone(timezone.utc)
    if (now-close_utc).total_seconds() > 5*86400:
        raise ValueError('최종 4시간 구간이 5일 초과')
    distance_pct = (close/lower-1)*100  # 음수=하단 아래, 양수=하단 위
    return result, distance_pct


def select(candidates, market, now, fetch, *, top_n=10):
    rows=[]; errors=[]
    for ticker,(name,risk) in candidates.items():
        try:
            frame=fetch(ticker)
            signal, distance=score_frame(frame,market,now)
            rows.append({'name':name,'symbol':ticker,'price':signal['last_price'],
                         'lower':signal['lower'],'upper':signal['upper'],
                         'distance_pct':round(distance,3),
                         'bar_close':signal['bar_close'],
                         'signal':'lower_break' if distance<=0 else 'near_lower',
                         'risk':risk+'; 밴드 하단 이탈 후 추가 하락 가능',
                         'currency':'KRW' if market['timezone']=='Asia/Seoul' else 'USD'})
        except Exception as e:
            errors.append(f'{ticker}: {str(e)[:90]}')
    # 가장 하단에 가까운 순서. 하단 아래로 지나치게 멀리 내려간 종목보다 가까운 종목 우선
    breaks=sorted((r for r in rows if r['distance_pct']<=0),key=lambda r:abs(r['distance_pct']))
    near=sorted((r for r in rows if r['distance_pct']>0),key=lambda r:r['distance_pct'])
    selected=(breaks+near)[:top_n]
    return selected,errors,len(rows)


def main():
    import yfinance as yf
    now=datetime.now(timezone.utc)
    payload={'generated_at':now.isoformat(),'method':'closed regular-market 4h/remaining-2.5h sessions, BB(20,2)',
             'selection':'fixed 25-symbol watchlist per market, lower-break first then proximity, up to 10',
             'markets':{}}
    for key, candidates in [('kr',KR),('us',US)]:
        market=MARKETS[key]
        # 단일 호출은 실패 격리를 위해 순차 처리. 개별 실패는 건너뛰고 원인 집계.
        def fetch(ticker):
            return yf.Ticker(ticker).history(period='35d',interval='60m',auto_adjust=False,
                                             prepost=False,raise_errors=True,timeout=12)
        picks,errors,valid=select(candidates,market,now,fetch)
        payload['markets'][key]={'picks':picks,'valid_count':valid,
                                 'scanned_count':len(candidates), 'error_count':len(errors),
                                 'errors':errors[:8],
                                 'status':'ok' if len(picks)>0 else 'insufficient'}
        print(f'{key}: 유효 {valid}/{len(candidates)}, 선정 {len(picks)}, 실패 {len(errors)}')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
