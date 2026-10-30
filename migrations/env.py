from alembic import context
from sqlalchemy import create_engine, pool
from dotenv import load_dotenv
import os
from carbon_coach.db_models import Base

load_dotenv()
config=context.config
url=config.attributes.get('database_url') or os.getenv('DATABASE_URL') or config.get_main_option('sqlalchemy.url')
if url.startswith('postgresql://'):
    url=url.replace('postgresql://','postgresql+psycopg://',1)
if context.is_offline_mode():
    context.configure(url=url,target_metadata=Base.metadata,literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine=create_engine(url,poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=Base.metadata,render_as_batch=engine.dialect.name=='sqlite')
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
