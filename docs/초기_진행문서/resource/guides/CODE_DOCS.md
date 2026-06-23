# 코드 작성 가이드라인

- 변수명 및 파일명은 스네이크 표기법으로 작성( example_file.py)
- 함수나 Method는 카멜 표기법으로 작성(myMethod)
- Class는 파스칼 표기법으로 작성(MyClass)
- (가능하면 표준단어 및 표준용어 사전을 정의하여 작성할 것)

## 필요성 
- 협업 시 코드의 일관성을 유지함으로 써 가독성 향상 및 유지보수 용이성 확보

<details open>
    <summary>표기법</summary>
    <details>
        <summary>변수/함수 명칭에 따른 표기법</summary>

1. <span style="color: red;">**파스칼 표기법(Pascal Case)**</span>
- 정의 : 카멜 표기법과 유사하지만, 첫 글자도 대문자로 표기
- 예시 : PascalCaseExample
- 활용 : 클래스명, 생성자명에 사용

2. 카멜 표기법(Camel Case)
- 정의: 여러 단어를 하나의 식별자로 표기할 때, 각 단어의 첫 글자를 대문자로 표기하고 나머지는 소문자로 표기하는 방법
-  예시 : camelCaseExample
- 활용 : 주로 변수명, 함수명에 사용

3) <span style="color: red;">**스네이크 표기법(Snake Case)**</span>
- 정의 : 여러 단어를 언더스코어로 구분하여 표기하는 방법
- 예시 : snake_case_example
- 활용 : 주로 변수명, 파일명에 사용

4) 스크래밍 스네이크 표기법(Screaming Snake Case)
- 정의 : 여러 단어를 언더스코어로 구분하고 문자 모두 대문자로 표기하는 방법
- 예시 : SCREAMING_SNAKE_CASE
- 활용 : 상수나 환경변수 정의에 사용

5) 케밥 표기법(Kebab Case)
- 정의 : 여러 단어를 –로 구분하고 문자를 모두 소문자로 표기하는 방법
- 예시 : kebab-case-example
- 활용 : 파일명, CSS명 일부

6). 헝가리안 표기법(Hungarian Notation)
- 정의 : 접두어에 자료형을 붙여 표기하는 방법
- 예시 : strHungarianNotation

---

</details>
<details>
    <summary>괄호 위치에 따른 분류</summary>


1) <span style="color: red;">K&R</span>
- 한 눈에 많은 코드를 볼 수 있음
- 수평으로 많은 코드를 작성할 수 있음
```python
if (...){
  처리1();
  처리2();
}
```
2) BSD

```python
if (...)
{
  처리1();
  처리2();
}
```
3) GNU
```python
if (...)
  {
    처리1();
    처리2();
  }
```
---

</details>

<details>
    <summary>코드 작성 예시</summary>

```python

# python Class 작성 예시
import torch
class Sample(torch.utils.data.Dataset):
    """
    클래스의 설명
    
    Attributes:
    -----------
    param : str
        파라미터의 설명

    Methods:
    ----------
    a() -> list:
        함수 기능 설명
    """
    def __init__(self, param: str):
        """
        클래스의 인스턴스 초기화

        Parameters:
        ----------
        param : str
            파라미터의 설명
        """
        self.param = param
        
    def myMethod(self) -> list:
        """
        함수 기능 설명

        Returns:
        ----------
        list
            반환값 설명
        """
        return []

```
---

</details>
</details>

---
- 이 코드 및 가이드라인 저작권 보호를 받으며, 무단 복제, 배포, 수정이 금지됩니다.
- 문의는 qkdrk777777@naver.com 으로 부탁드리겠습니다.


