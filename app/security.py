from passlib.context import CryptContext
pwd=CryptContext(schemes=["bcrypt"],deprecated="auto")
def hash_password(v:str)->str:return pwd.hash(v)
def verify_password(v:str,h:str)->bool:return pwd.verify(v,h)
