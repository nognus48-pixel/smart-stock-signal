# -*- coding: utf-8 -*-
"""Archive a completed stock screen and optionally publish one Blogger post per date.
Requires latest docs/picks.json from the regular update workflow.
No real orders, and no invented prices. Never overwrites historical snapshots.
"""
import os, json, sys, html, time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/'docs'/'history'
SEOUL=ZoneInfo('Asia/Seoul')

def request_json(url, method='GET', payload=None, token=None):
    headers={'Accept':'application/json','User-Agent':'SmartStockLabArchive/1.0'}
    if payload is not None: headers['Content-Type']='application/json; charset=utf-8'
    if token: headers['Authorization']='Bearer '+token
    body=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
    req=Request(url,data=body,headers=headers,method=method)
    with urlopen(req,timeout=25) as resp:
        return json.load(resp)

def load_snapshot():
    path=ROOT/'docs'/'picks.json'
    if not path.exists(): raise RuntimeError('docs/picks.json이 없습니다. 먼저 최신 시세 업데이트를 실행하세요.')
    data=json.loads(path.read_text(encoding='utf-8'))
    stamp=datetime.fromisoformat(data['generated_at'].replace('Z','+00:00'))
    now=datetime.now(timezone.utc)
    if stamp.tzinfo is None: raise RuntimeError('generated_at에 시간대가 없습니다')
    if abs((now-stamp).total_seconds())>4*3600: raise RuntimeError('종목 데이터가 4시간 이내 갱신되지 않았습니다. 아카이브 취소')
    markets=data.get('markets') or {}
    for market in ('kr','us'):
        part=markets.get(market) or {}
        if part.get('status')!='ok' or not part.get('picks'):
            raise RuntimeError(f'{market}: 유효한 추천 후보 데이터가 없습니다. 빈 글 저장 방지')
    return data

def market_rows(data,key):
    src=data['markets'][key]['picks']
    # Copy the exact data and save the captured order, 100 max.
    return [dict(row) for row in src[:100]]

def get_date():
    # Weekday schedule Tue-Sat 09:30 KST, creates snapshot for the prior KST day.
    return (datetime.now(SEOUL).date()-timedelta(days=1)).isoformat()

def safe_num(value,unit):
    try: return f'{float(value):,.0f}원' if unit=='KRW' else f'${float(value):,.2f}'
    except (ValueError,TypeError):return '정보 없음'

def clean(s):
    import re
    s=str(s or '')
    for _ in range(4): s=html.unescape(s)
    s=re.sub(r'(?i)(?:위험요인\s*[:：·-]?\s*)+','',s).strip()
    return html.escape(s)

def page_html(snapshot):
    parts=[f'<h2>{html.escape(snapshot["archive_date"])} 종목 분석 기록</h2>',
      '<p>당일 확정 시점의 분석 후보를 보존한 기록입니다. 매수 권유가 아니며 이후 변경되지 않습니다.</p>',
      f'<p>수집 시각: {html.escape(snapshot["captured_at_kst"])} · 종목 데이터 기준: {html.escape(snapshot["source_generated_at"])}</p>']
    for key,title in [('kr','한국 주식'),('us','미국 주식')]:
        rows=snapshot['markets'][key]
        parts.append(f'<h3>{title} — {len(rows)}개</h3>')
        parts.append('<table style="border-collapse:collapse;width:100%;font-size:13px"><thead><tr><th>종목</th><th>가격</th><th>밴드 하단</th><th>거리</th><th>구분</th><th>위험요인</th></tr></thead><tbody>')
        for row in rows:
            currency=row.get('currency','KRW' if key=='kr' else 'USD')
            try: dist=f'{float(row.get("distance_pct")):.2f}%'
            except (TypeError,ValueError):dist='-'
            sig='하단 이탈' if row.get('signal')=='lower_break' else '하단 접근'
            name=html.escape(str(row.get('name') or row.get('symbol') or ''))
            sym=html.escape(str(row.get('symbol') or ''))
            parts.append('<tr>'+''.join(f'<td style="border:1px solid #e5e7eb;padding:7px">{val}</td>' for val in [name+' ('+sym+')',safe_num(row.get('price'),currency),safe_num(row.get('lower'),currency),dist,sig,clean(row.get('risk'))])+'</tr>')
        parts.append('</tbody></table>')
    parts.append('<p style="font-size:12px;color:#667085">정규장 4시간 단위 볼린저밴드 분석 후보이며, 무료 데이터 수집 시점과 거래 시각이 다를 수 있습니다. 지연·누락·추가 하락 위험이 있습니다.</p>')
    return '\n'.join(parts)

def get_token():
    cid=os.getenv('BLOGGER_CLIENT_ID','').strip()
    secret=os.getenv('BLOGGER_CLIENT_SECRET','').strip()
    refresh=os.getenv('BLOGGER_REFRESH_TOKEN','').strip()
    blogid=os.getenv('BLOGGER_BLOG_ID','').strip()
    if not all((cid,secret,refresh,blogid)):
        print('Blogger OAuth 설정 미완료: GitHub 날짜별 기록만 보존합니다.')
        return None,None
    from urllib.parse import urlencode
    payload=urlencode({'client_id':cid,'client_secret':secret,'refresh_token':refresh,'grant_type':'refresh_token'}).encode()
    req=Request('https://oauth2.googleapis.com/token',data=payload,headers={'Content-Type':'application/x-www-form-urlencoded'})
    with urlopen(req,timeout=25) as res: token=json.load(res)['access_token']
    return token,blogid

def publish_once(snapshot,token,blogid):
    title=f'[스마트 주식연구소] {snapshot["archive_date"]} 일별 종목 분석 기록'
    base=f'https://www.googleapis.com/blogger/v3/blogs/{blogid}/posts'
    # Check latest 100 posts for the exact title. Prevent most duplicate publishing.
    from urllib.parse import urlencode
    cursor=None
    for _ in range(5):
        args={'maxResults':100,'fetchBodies':'false','status':'live'}
        if cursor:args['pageToken']=cursor
        page=request_json(base+'?'+urlencode(args),token=token)
        for post in page.get('items',[]):
            if post.get('title')==title:
                print('이미 게시된 글 확인: '+str(post.get('url')))
                return post.get('url','')
        cursor=page.get('nextPageToken')
        if not cursor:break
    article={'kind':'blogger#post','title':title,'content':page_html(snapshot),'labels':['일별 종목분석','분석 기록']}
    result=request_json(base,method='POST',payload=article,token=token)
    print('Blogger 게시 완료:',result.get('url',''))
    return result.get('url','')

def main():
    day=get_date()
    if os.getenv('ARCHIVE_DATE'):
        raise RuntimeError('과거 날짜를 임의로 입력해 최신 시세로 소급 기록하는 것은 지원하지 않습니다.')
    HISTORY.mkdir(parents=True,exist_ok=True)
    dest=HISTORY/f'{day}.json'
    if dest.exists():
        snapshot=json.loads(dest.read_text(encoding='utf-8'))
        print('기존 날짜 기록을 그대로 사용:',dest)
    else:
        data=load_snapshot()
        snapshot={'schema':1,'archive_date':day,'captured_at_kst':datetime.now(SEOUL).isoformat(timespec='seconds'),
           'source_generated_at':data['generated_at'],
           'markets':{'kr':market_rows(data,'kr'),'us':market_rows(data,'us')}}
        dest.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('날짜별 기록 생성:',dest,'한국',len(snapshot['markets']['kr']),'미국',len(snapshot['markets']['us']))
    token,blogid=get_token()
    if token:
        try:publish_once(snapshot,token,blogid)
        except (HTTPError,Exception) as exc:
            print('Blogger 자동 발행 실패 (날짜별 데이터 기록은 유지):',repr(exc),file=sys.stderr)
            # Do not treat this as success: operator should review OAuth settings.
            raise

if __name__=='__main__':main()
