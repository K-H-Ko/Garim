"""
worker_event.py — 워커 신호용 전역 Event 싱글톤

job 생성 시 event.set() → 워커가 즉시 깨어남
대기 중엔 event.wait()으로 CPU 0% 사용
"""
import threading

# 서버 전체에서 공유하는 단일 Event 객체
WORKER_EVENT = threading.Event()
