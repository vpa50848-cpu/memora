from api.index import Base, engine
if engine is None:
    raise SystemExit("Set DATABASE_URL first.")
Base.metadata.create_all(bind=engine)
print("MEMORA database tables created.")
