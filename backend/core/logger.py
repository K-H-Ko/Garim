import logging

def setup_logging():
    root = logging.getLogger()
    
    # nodemon 실행시 로그가 추가로 나오는 것 방지하기 위한 조건문
    if root.handlers:
        root.handlers.clear()
    
    logging.basicConfig(
        ## 로거 레벨
        # 레벨	        숫자값	        의미
        # CRITICAL	    50	        시스템이 거의 죽은 수준 (즉시 대응 필요)
        # ERROR	        40	        기능 실패 (예외 발생)
        # WARNING	    30	        문제 가능성 있음 (경고)
        # INFO	        20	        정상 동작 정보
        # DEBUG	        10	        디버깅용 상세 정보
        # NOTSET	    0	        설정 없음 (상위 logger 따름)
        
        level=logging.INFO,

        ## 로그 관련 내용
        #     필드	                의미	                    예시
        # %(message)s	        실제 로그 메시지	        "user created"
        # %(levelname)s	        로그 레벨 이름	            INFO, ERROR
        # %(levelno)s	        로그 레벨 숫자	            20, 40
        
        ## 시간 관련
        #     필드	                의미	          
        # %(asctime)s	        사람이 읽을 수 있는 시간
        # %(created)f	        epoch timestamp
        # %(relativeCreated)d	프로그램 시작 이후 ms
        
        ## logger / 모듈 관련
        #     필드	                의미	          
        # %(name)s	        logger 이름 (__name__)
        # %(module)s	    모듈 이름 (파일명)
        # %(filename)s	    파일 이름
        # %(pathname)s	    전체 경로
        # %(funcName)s	    함수 이름
        # %(lineno)d	    라인 번호
        
        ## 실행 컨텍스트
        # %(process)d	    프로세스 ID
        # %(processName)s	프로세스 이름
        # %(thread)d	    스레드 ID
        # %(threadName)s	스레드 이름
        
        ## 기타
        # %(stack_info)s	스택 정보
        # %(exc_info)s	    예외 정보
        
        format="%(asctime)s - %(name)s [%(funcName)s] : %(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )