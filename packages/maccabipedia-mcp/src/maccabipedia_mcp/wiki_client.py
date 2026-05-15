from __future__ import annotations

from typing import Any

import requests

from maccabipedia_mcp.config import Config


class WikiClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._session = requests.Session()
        self._csrf_token: str | None = None

    @property
    def _api(self) -> str:
        return self._config.api_url

    def _get(self, params: dict[str, Any]) -> requests.Response:
        params.setdefault("format", "json")
        return self._session.get(self._api, params=params)

    def _check_json(self, resp: requests.Response) -> dict | None:
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" not in content_type and "text/json" not in content_type:
            return {
                "error": True,
                "code": "non_json",
                "message": f"MediaWiki API returned non-JSON response (Content-Type: {content_type})",
            }
        api_error = resp.json().get("error")
        if api_error:
            return {
                "error": True,
                "code": api_error.get("code", "api_error"),
                "message": api_error.get("info", "MediaWiki API returned an error"),
            }
        return None

    # -- Cargo tools --

    def list_cargo_tables(self) -> list[str] | dict:
        resp = self._get({"action": "cargotables"})
        err = self._check_json(resp)
        if err:
            return err
        return resp.json()["cargotables"]

    def describe_cargo_table(self, table: str) -> list[dict[str, str]] | dict:
        resp = self._get({"action": "cargofields", "table": table})
        err = self._check_json(resp)
        if err:
            return err
        fields = resp.json()["cargofields"]
        return [
            {"name": name, "type": ftype["type"] if isinstance(ftype, dict) else ftype}
            for name, ftype in fields.items()
        ]

    @staticmethod
    def _fix_cargo_field_aliases(fields: str) -> str:
        """Auto-alias fields whose alias would start with '_'.

        The Cargo API rejects aliases starting with underscore.
        E.g. ``_pageName`` becomes ``_pageName=pageName``,
        but ``Table._pageName=MyAlias`` is left alone (alias is fine).
        """
        fixed = []
        for field in fields.split(","):
            field = field.strip()
            if "=" in field:
                # Explicit alias — leave as-is
                fixed.append(field)
            else:
                # Effective alias is the part after the last dot, or the whole field
                alias = field.rsplit(".", 1)[-1]
                if alias.startswith("_"):
                    fixed.append(f"{field}={alias.lstrip('_')}")
                else:
                    fixed.append(field)
        return ",".join(fixed)

    def query_cargo(
        self,
        tables: str,
        fields: str,
        where: str | None = None,
        join_on: str | None = None,
        group_by: str | None = None,
        having: str | None = None,
        order_by: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict] | dict:
        fields = self._fix_cargo_field_aliases(fields)
        params: dict[str, Any] = {
            "action": "cargoquery",
            "tables": tables,
            "fields": fields,
            "limit": limit,
            "offset": offset,
        }
        if where:
            params["where"] = where
        if join_on:
            params["join_on"] = join_on
        if group_by:
            params["group_by"] = group_by
        if having:
            params["having"] = having
        if order_by:
            params["order_by"] = order_by

        resp = self._get(params)
        err = self._check_json(resp)
        if err:
            return err

        data = resp.json()
        return [row["title"] for row in data.get("cargoquery", [])]

    def _post(self, data: dict[str, Any]) -> requests.Response:
        data.setdefault("format", "json")
        return self._session.post(self._api, data=data)

    # -- Auth --

    def _ensure_authenticated(self) -> dict | None:
        if self._csrf_token:
            return None
        if not self._config.username or not self._config.password:
            return {"error": True, "code": "no_credentials", "message": "No credentials configured — set MACCABIPEDIA_BOT_USERNAME and MACCABIPEDIA_BOT_PASSWORD"}

        # Step 1: get login token
        resp = self._get({"action": "query", "meta": "tokens", "type": "login"})
        login_token = resp.json()["query"]["tokens"]["logintoken"]

        # Step 2: login
        resp = self._post({
            "action": "login",
            "lgname": self._config.username,
            "lgpassword": self._config.password,
            "lgtoken": login_token,
        })
        login_result = resp.json().get("login", {})
        if login_result.get("result") != "Success":
            return {"error": True, "code": "login_failed", "message": f"Login failed: {login_result.get('reason', 'unknown')}"}

        # Step 3: get CSRF token
        self._fetch_csrf_token()
        return None

    def _fetch_csrf_token(self) -> None:
        resp = self._get({"action": "query", "meta": "tokens", "type": "csrf"})
        self._csrf_token = resp.json()["query"]["tokens"]["csrftoken"]

    def _do_edit(self, params: dict[str, Any], retry: bool = True) -> dict:
        auth_err = self._ensure_authenticated()
        if auth_err:
            return auth_err

        params["token"] = self._csrf_token
        params["action"] = "edit"
        resp = self._post(params)
        data = resp.json()

        if "error" in data:
            if data["error"]["code"] == "badtoken" and retry:
                self._fetch_csrf_token()
                return self._do_edit(params, retry=False)
            return {"error": True, "code": data["error"]["code"], "message": data["error"]["info"]}

        edit = data["edit"]
        return {"success": True, "title": edit["title"], "revid": edit.get("newrevid")}

    # -- Page write tools --

    def create_page(self, title: str, text: str, summary: str) -> dict:
        return self._do_edit({"title": title, "text": text, "summary": summary, "createonly": "1"})

    def edit_page(self, title: str, text: str, summary: str) -> dict:
        return self._do_edit({"title": title, "text": text, "summary": summary, "nocreate": "1"})

    def upload_file(self, filename: str, file_path: str, text: str, comment: str) -> dict:
        auth_err = self._ensure_authenticated()
        if auth_err:
            return auth_err

        with open(file_path, "rb") as f:
            file_data = f.read()

        resp = self._session.post(
            self._api,
            data={
                "action": "upload",
                "filename": filename,
                "comment": comment,
                "text": text,
                "token": self._csrf_token,
                "ignorewarnings": "1",
                "format": "json",
            },
            files={"file": (filename, file_data)},
        )
        data = resp.json()
        if "error" in data:
            return {"error": True, "code": data["error"]["code"], "message": data["error"]["info"]}
        upload = data["upload"]
        if upload.get("result") != "Success":
            return {"error": True, "code": "upload_failed", "message": f"Upload failed: {upload.get('result')}"}
        return {"success": True, "filename": upload["filename"]}

    def purge_pages(self, titles: list[str]) -> list[dict]:
        results = []
        # Batch in groups of 50
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            resp = self._post({
                "action": "purge",
                "titles": "|".join(batch),
                "forcelinkupdate": "1",
            })
            for item in resp.json().get("purge", []):
                results.append({"title": item["title"], "purged": "purged" in item})
        return results

    # -- Page read tools --

    def get_page(self, title: str) -> dict:
        resp = self._get({
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvprop": "content",
            "redirects": "1",
        })
        data = resp.json()
        pages = data["query"]["pages"]
        page = next(iter(pages.values()))

        if "missing" in page:
            return {"exists": False, "pageid": None, "ns": None, "title": title, "wikitext": "", "redirect_target": None}

        redirect_target = None
        redirects = data["query"].get("redirects", [])
        for r in redirects:
            if r["from"] == title:
                redirect_target = r["to"]
                break

        wikitext = page.get("revisions", [{}])[0].get("*", "")
        return {
            "exists": True,
            "pageid": page.get("pageid"),
            "ns": page.get("ns"),
            "title": page["title"],
            "wikitext": wikitext,
            "redirect_target": redirect_target,
        }

    def page_exists(self, title: str) -> dict:
        resp = self._get({"action": "query", "titles": title})
        pages = resp.json()["query"]["pages"]
        page = next(iter(pages.values()))
        exists = "missing" not in page
        redirect = "redirect" in page
        return {"exists": exists, "pageid": page.get("pageid"), "redirect": redirect}

    def search_pages(self, query: str, namespace: int | None = 0, limit: int = 500) -> dict:
        if limit <= 0:
            return {"total_hits": 0, "results": []}
        # Strip embedded quotes so the outer phrase wrapping stays balanced.
        phrase = query.replace('"', "")
        # MediaWiki's 'srnamespace=*' expands to every namespace (including
        # custom ones like Maccabipedia's ns=3000 songs). Omitting the param
        # is NOT equivalent — that defaults to ns=0 only.
        srnamespace: str | int = "*" if namespace is None else namespace
        params: dict[str, Any] = {
            "action": "query",
            "list": "search",
            "srsearch": f'"{phrase}"',
            "srnamespace": srnamespace,
            "srlimit": min(limit, 500),
            "srwhat": "text",
            "formatversion": 2,
        }
        results: list[dict] = []
        total_hits = 0

        while len(results) < limit:
            resp = self._get(params)
            json_err = self._check_json(resp)
            if json_err:
                return json_err

            data = resp.json()
            if "error" in data:
                return {
                    "error": True,
                    "code": data["error"]["code"],
                    "message": data["error"]["info"],
                }

            query_data = data.get("query", {})
            total_hits = query_data.get("searchinfo", {}).get("totalhits", total_hits)
            page_hits = query_data.get("search", [])
            if not page_hits:
                break

            remaining = limit - len(results)
            for hit in page_hits[:remaining]:
                results.append({
                    "pageid": hit["pageid"],
                    "title": hit["title"],
                    "snippet": hit.get("snippet", ""),
                })

            next_offset = data.get("continue", {}).get("sroffset")
            if next_offset is None or next_offset == params.get("sroffset"):
                break
            params["sroffset"] = next_offset

        return {"total_hits": total_hits, "results": results}

    def list_category_pages(self, category: str, limit: int = 50) -> list[str]:
        if not category.startswith("קטגוריה:"):
            category = f"קטגוריה:{category}"
        resp = self._get({
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": limit,
            "cmprop": "ids|title|type",
        })
        return [
            {"pageid": m["pageid"], "ns": m["ns"], "title": m["title"], "type": m.get("type", "page")}
            for m in resp.json()["query"]["categorymembers"]
        ]
