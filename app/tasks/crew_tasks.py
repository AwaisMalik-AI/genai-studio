from app.services.content_crew import ContentCrew
from app.tasks.celery_app import celery_app


@celery_app.task(name="genai.run_content_crew")
def run_content_crew_task(brief: str, style: str = "professional") -> dict:
    result = ContentCrew().run(brief, style)
    return {"crew": result.crew, "used_llm": result.used_llm, "steps": result.steps, "final": result.final}
