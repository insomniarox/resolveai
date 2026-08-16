from resolve_ai.retrieval import search_runbooks

results = search_runbooks(
    database_url="postgresql://resolveai:resolveai@localhost:5432/resolveai",
    query='"connection pool" OR timeout',
    limit=3,
)
print(results)
