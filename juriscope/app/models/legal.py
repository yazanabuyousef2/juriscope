from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    country_id: Mapped[int] = mapped_column(
        ForeignKey("countries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    jurisdiction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title_ar: Mapped[str] = mapped_column(String(500), nullable=False)
    title_en: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    document_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="law",
    )
    # law, regulation, instruction, decision, case_law, court_principle, doctrine

    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    official_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    issue_date: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    effective_date: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    # active, amended, repealed, archived

    review_status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    # draft, pending_review, approved, rejected, archived

    source_confidence: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    # low, medium, high, official

    uploaded_file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    articles: Mapped[list["LegalArticle"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class LegalArticle(Base):
    __tablename__ = "legal_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("legal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    country_id: Mapped[int] = mapped_column(
        ForeignKey("countries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    article_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    article_title: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    article_text: Mapped[str] = mapped_column(Text, nullable=False)
    article_text_clean: Mapped[str] = mapped_column(Text, nullable=False, default="")

    chapter: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    section: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    # active, amended, repealed, archived

    review_status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    # draft, pending_review, approved, rejected, archived

    effective_date: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    repealed_date: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    source_confidence: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    document: Mapped["LegalDocument"] = relationship(back_populates="articles")

    versions: Mapped[list["LegalArticleVersion"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    topics: Mapped[list["LegalArticleTopic"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    keywords: Mapped[list["LegalArticleKeyword"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    relations: Mapped[list["LegalArticleRelation"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )


class LegalArticleVersion(Base):
    __tablename__ = "legal_article_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    article_id: Mapped[int] = mapped_column(
        ForeignKey("legal_articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    article_text: Mapped[str] = mapped_column(Text, nullable=False)
    article_text_clean: Mapped[str] = mapped_column(Text, nullable=False, default="")

    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="archived")
    # active, archived

    effective_date: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    article: Mapped["LegalArticle"] = relationship(back_populates="versions")


class LegalTopic(Base):
    __tablename__ = "legal_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("legal_topics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    article_links: Mapped[list["LegalArticleTopic"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )


class LegalArticleTopic(Base):
    __tablename__ = "legal_article_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    article_id: Mapped[int] = mapped_column(
        ForeignKey("legal_articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    topic_id: Mapped[int] = mapped_column(
        ForeignKey("legal_topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    article: Mapped["LegalArticle"] = relationship(back_populates="topics")
    topic: Mapped["LegalTopic"] = relationship(back_populates="article_links")

    __table_args__ = (
        UniqueConstraint("article_id", "topic_id", name="uq_legal_article_topic"),
    )


class LegalArticleKeyword(Base):
    __tablename__ = "legal_article_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    article_id: Mapped[int] = mapped_column(
        ForeignKey("legal_articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    keyword_type: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    # general, alias, synonym, phrase, legal_term

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    article: Mapped["LegalArticle"] = relationship(back_populates="keywords")


class LegalArticleRelation(Base):
    __tablename__ = "legal_article_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    article_id: Mapped[int] = mapped_column(
        ForeignKey("legal_articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    relation_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # link, amendment, case_law, related_legislation, interpretation, raw_note

    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    article: Mapped["LegalArticle"] = relationship(back_populates="relations")


class LegalImportJob(Base):
    __tablename__ = "legal_import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    country_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("countries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    staff_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # pending, processing, completed, failed

    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)