"""Async wrapper around Moodle's REST Web Services API.

Phase 1 (current): read-only calls against Moodle's built-in webservice
functions. Phase 2 (later, only if needed): a few extra calls to a custom
local plugin's endpoints for write-back actions Moodle's default API can't
do (e.g. pushing a generated quiz back into a course).
"""
import httpx

from app.config import settings

REST_ENDPOINT = "/webservice/rest/server.php"


class MoodleClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or settings.moodle_base_url).rstrip("/")
        self.token = token or settings.moodle_ws_token

    async def _call(self, wsfunction: str, **params) -> dict:
        query = {
            "wstoken": self.token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
            **params,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}{REST_ENDPOINT}", params=query)
            resp.raise_for_status()
            return resp.json()

    async def get_site_info(self) -> dict:
        return await self._call("core_webservice_get_site_info")

    async def get_course_contents(self, course_id: int) -> dict:
        return await self._call("core_course_get_contents", courseid=course_id)

    async def get_enrolled_users(self, course_id: int) -> dict:
        return await self._call("core_enrol_get_enrolled_users", courseid=course_id)

    async def get_grade_items(self, course_id: int, user_id: int) -> dict:
        return await self._call(
            "gradereport_user_get_grade_items", courseid=course_id, userid=user_id
        )

    async def get_quizzes_by_course(self, course_id: int) -> dict:
        return await self._call("mod_quiz_get_quizzes_by_courses", **{"courseids[0]": course_id})
