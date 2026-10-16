from datetime import datetime
from sqlalchemy import String,Integer,Float,DateTime,ForeignKey,Boolean,Text,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base

class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(160))
    cpf:Mapped[str|None]=mapped_column(String(20),nullable=True,unique=True)
    email:Mapped[str]=mapped_column(String(180),unique=True,index=True)
    password_hash:Mapped[str]=mapped_column(String(255))
    role:Mapped[str]=mapped_column(String(60),default="Participante")
    phone:Mapped[str]=mapped_column(String(30),default="")
    language:Mapped[str]=mapped_column(String(5),default="pt")
    access_status:Mapped[str]=mapped_column(String(20),default="AUTORIZADO")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Event(Base):
    __tablename__="events"
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(30),unique=True,index=True)
    cover_path:Mapped[str]=mapped_column(String(500),default="")
    name:Mapped[str]=mapped_column(String(180))
    summary:Mapped[str]=mapped_column(Text,default="")
    period:Mapped[str]=mapped_column(String(100),default="")
    location:Mapped[str]=mapped_column(String(180),default="")
    capacity:Mapped[int]=mapped_column(Integer,default=0)
    keyword:Mapped[str]=mapped_column(String(80),default="GERAL")
    schedule_synopsis:Mapped[str]=mapped_column(Text,default="")
    status:Mapped[str]=mapped_column(String(40),default="RASCUNHO")
    payment_mode:Mapped[str]=mapped_column(String(20),default="MANUAL")
    pix_key:Mapped[str]=mapped_column(String(180),default="")
    pix_receiver:Mapped[str]=mapped_column(String(180),default="")
    pix_provider:Mapped[str]=mapped_column(String(80),default="")
    pix_environment:Mapped[str]=mapped_column(String(30),default="TESTE")
    payment_deadline_minutes:Mapped[int]=mapped_column(Integer,default=20)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Activity(Base):
    __tablename__="activities"
    id:Mapped[int]=mapped_column(primary_key=True)
    event_id:Mapped[int]=mapped_column(ForeignKey("events.id",ondelete="CASCADE"))
    date:Mapped[str]=mapped_column(String(20),default="")
    start_time:Mapped[str]=mapped_column(String(10),default="")
    end_time:Mapped[str]=mapped_column(String(10),default="")
    activity_type:Mapped[str]=mapped_column(String(60),default="Palestra")
    location:Mapped[str]=mapped_column(String(180),default="")
    modality:Mapped[str]=mapped_column(String(30),default="Presencial")
    electronic_address:Mapped[str]=mapped_column(String(500),default="")
    speaker:Mapped[str]=mapped_column(String(180),default="")
    speaker_image_path:Mapped[str]=mapped_column(String(500),default="")
    curriculum:Mapped[str]=mapped_column(Text,default="")
    syllabus:Mapped[str]=mapped_column(Text,default="")
    short_synopsis:Mapped[str]=mapped_column(Text,default="")
    capacity:Mapped[int]=mapped_column(Integer,default=0)
    specific_capacity:Mapped[int]=mapped_column(Integer,default=0)
    workload_minutes:Mapped[int]=mapped_column(Integer,default=0)
    price_model:Mapped[str]=mapped_column(String(20),default="Gratis")
    price:Mapped[float]=mapped_column(Float,default=0)

class Enrollment(Base):
    __tablename__="enrollments"
    __table_args__=(UniqueConstraint("user_id","activity_id",name="uq_enrollment_user_activity"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    event_id:Mapped[int]=mapped_column(ForeignKey("events.id"))
    activity_id:Mapped[int]=mapped_column(ForeignKey("activities.id"))
    status:Mapped[str]=mapped_column(String(30),default="CONFIRMADA")
    attendance:Mapped[str]=mapped_column(String(20),default="NAO_REGISTRADA")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Payment(Base):
    __tablename__="payments"
    id:Mapped[int]=mapped_column(primary_key=True)
    event_id:Mapped[int]=mapped_column(ForeignKey("events.id"))
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    amount:Mapped[float]=mapped_column(Float,default=0)
    method:Mapped[str]=mapped_column(String(20),default="MANUAL")
    provider_code:Mapped[str]=mapped_column(String(180),default="")
    receipt_path:Mapped[str]=mapped_column(String(500),default="")
    status:Mapped[str]=mapped_column(String(30),default="PENDENTE")
    paid_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Refund(Base):
    __tablename__="refunds"
    id:Mapped[int]=mapped_column(primary_key=True)
    payment_id:Mapped[int]=mapped_column(ForeignKey("payments.id"))
    activity_id:Mapped[int|None]=mapped_column(ForeignKey("activities.id"),nullable=True)
    admin_id:Mapped[int]=mapped_column(ForeignKey("users.id"))
    amount:Mapped[float]=mapped_column(Float)
    receipt_path:Mapped[str]=mapped_column(String(500),default="")
    note:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class Permission(Base):
    __tablename__="permissions"
    id:Mapped[int]=mapped_column(primary_key=True)
    role:Mapped[str]=mapped_column(String(60),index=True)
    permission:Mapped[str]=mapped_column(String(100),index=True)
    allowed:Mapped[bool]=mapped_column(Boolean,default=False)

class Theme(Base):
    __tablename__="theme"
    id:Mapped[int]=mapped_column(primary_key=True)
    page_bg:Mapped[str]=mapped_column(String(20),default="#f4f6f8")
    panel_bg:Mapped[str]=mapped_column(String(20),default="#ffffff")
    title_color:Mapped[str]=mapped_column(String(20),default="#17212b")
    title_bg:Mapped[str]=mapped_column(String(20),default="#ffffff")
    card_bg:Mapped[str]=mapped_column(String(20),default="#ffffff")

class CertificateModel(Base):
    __tablename__="certificate_models"
    id:Mapped[int]=mapped_column(primary_key=True)
    filename:Mapped[str]=mapped_column(String(255),unique=True)
    storage_path:Mapped[str]=mapped_column(String(500))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class CertificateConfig(Base):
    __tablename__="certificate_configs"
    event_id:Mapped[int]=mapped_column(ForeignKey("events.id"),primary_key=True)
    signature_type:Mapped[str]=mapped_column(String(20),default="AUTOMATICA")
    email_subject:Mapped[str]=mapped_column(String(255),default="Seu certificado - {{EVENTO}}")
    email_body:Mapped[str]=mapped_column(Text,default="Olá {{NOME}}, agradecemos sua participação em {{EVENTO}}. Certificado: {{LINK_CERTIFICADO}} Código: {{CODIGO_CREDENCIAL}} URL: {{URL_CREDENCIAL}}")

class Certificate(Base):
    __tablename__="certificates"
    id:Mapped[int]=mapped_column(primary_key=True)
    enrollment_id:Mapped[int]=mapped_column(ForeignKey("enrollments.id"),unique=True)
    model_id:Mapped[int|None]=mapped_column(ForeignKey("certificate_models.id"),nullable=True)
    status:Mapped[str]=mapped_column(String(20),default="PENDENTE")
    credential_code:Mapped[str]=mapped_column(String(80),default="")
    credential_url:Mapped[str]=mapped_column(String(500),default="")
    file_path:Mapped[str]=mapped_column(String(500),default="")
    participant_area:Mapped[bool]=mapped_column(Boolean,default=False)
    error:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
