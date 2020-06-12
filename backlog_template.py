from datetime import datetime, timedelta
from logging import INFO, basicConfig, getLogger

import fire
from keyring import get_password, set_password, delete_password
import requests
import toml

logger = getLogger(__name__)
SERVICE_NAME = "backlog-template-API_KEY"


class BaseAPI:
    def get(self, end_point, params={}):
        r = requests.get(end_point, params=params)
        r.raise_for_status()
        return r

    def post(self, end_point, data, params={}):
        r = requests.post(end_point, data, params=params)
        r.raise_for_status()
        return r


class BacklogSpace(BaseAPI):
    def __init__(self, space_domain):
        self.space_domain = space_domain
        self.base_url = "https://" + space_domain + "/api/v2/"
        api_key = get_password(service_name=SERVICE_NAME, username=self.space_domain)
        assert api_key, "API_KEY for {} is not stored yet.".format(space_domain)
        self.api_key = api_key

    def get_prop(self, property_name):
        return self.get(
            end_point=self.base_url + property_name, params={"apiKey": self.api_key},
        )


class BacklogProject(BacklogSpace):
    """
    Backlog API (V2)
    https://developer.nulab.com/ja/docs/backlog/#backlog-api-とは
    """

    mandatory_keys = ("summary", "issueType", "priority")

    substituted_keys = {
        "priority": "priorities",
        "issueType": "pj_issue_types",
        "version": "pj_versions",
        "milestone": "pj_versions",
        "assignee": "pj_users",
    }

    date_keys = ("dueDate",)

    def __init__(self, space_domain, project_key):
        def index(response, key="name", value="id"):
            return {d[key]: d[value] for d in response.json()}

        super().__init__(space_domain)
        logger.info(
            "Fetching data from {} (PROJECT_KEY={}).".format(space_domain, project_key)
        )
        self.project_id = index(self.get_prop("projects"), key="projectKey")[
            project_key
        ]
        self.priorities = index(self.get_prop("priorities"))
        self.pj_issue_types = index(self.get_pj_prop("issueTypes"))
        self.pj_versions = index(self.get_pj_prop("versions"))
        self.pj_users = index(self.get_pj_prop("users"))

    def get_pj_prop(self, property_name):
        return self.get(
            end_point=self.base_url + f"projects/{self.project_id}/{property_name}",
            params={"apiKey": self.api_key},
        )

    def post_issue(self, issue):
        dates = {k: issue[k].strftime("%Y-%m-%d") for k in self.date_keys if k in issue}
        return self.post(
            end_point=self.base_url + "issues",
            data={
                "projectId": self.project_id,
                "summary": issue["summary"],
                "issueTypeId": self.pj_issue_types[issue["issueType"]],
                "priorityId": self.priorities[issue["priority"]],
                "parentIssueId": issue.get("parentIssueId"),
                "description": issue.get("description"),
                "dueDate": dates.get("dueDate"),
                "versionId[]": self.pj_versions.get(issue.get("version")),
                "milestoneId[]": self.pj_versions.get(issue.get("milestone")),
                "assigneeId": self.pj_users.get(issue.get("assignee")),
            },
            params={"apiKey": self.api_key},
        )

    def post_affiliated_issues(self, template):
        def convert_date_by_delta(d):
            for k in self.date_keys:
                if k not in d or isinstance(d[k], datetime):
                    continue
                elif isinstance(d[k], dict):
                    d[k] = template["config"]["basedate"] + timedelta(**d[k])
                else:
                    raise ValueError(f"value of {k} must be datetime or dict")
            return d

        def replace_curly_braces(d):
            if "repl" not in template.get("config"):
                return d
            repl = template["config"]["repl"]
            replaced = {}
            for k, v in d.items():
                if isinstance(d[k], datetime):
                    replaced[k] = v
                else:
                    replaced[k] = v.format(**repl)
            return replaced

        for affiliated_issue in template["issues"]:
            parent = affiliated_issue
            children = parent.pop("children", [])

            parent = convert_date_by_delta(parent)
            parent = replace_curly_braces(parent)
            self.__validate_issue(parent)
            r = self.post_issue(parent).json()
            logger.info("Posted '{} {}'.".format(r["issueKey"], parent["summary"]))
            parentIssueId = r["id"]

            children = [convert_date_by_delta(child) for child in children]
            children = [replace_curly_braces(child) for child in children]
            [self.__validate_issue(child) for child in children]
            for child in children:
                child.update({"parentIssueId": parentIssueId})
                rc = self.post_issue(child).json()
                logger.info(
                    "Posted (child issue of {}) '{} {}'.".format(
                        r["issueKey"], rc["issueKey"], child["summary"]
                    )
                )

    def __validate_issue(self, issue):
        for k in self.mandatory_keys:
            assert k in issue, "Template is missing a mandatory key '{}'".format(k)

        for k, v in self.substituted_keys.items():
            if k not in issue:
                continue
            assert issue[k] in getattr(
                self, v
            ), "'{}' is not a valid key for '{}'".format(issue[k], k)


class BacklogProjectCLI:
    def post(self, path_to_template):
        def prepost_check(template):
            SPACE_DOMAIN = template["target"].pop("SPACE_DOMAIN")
            PROJECT_KEY = template["target"].pop("PROJECT_KEY")
            if "basedate" in template.get("config"):
                print("--- Base date-time ---")
                print(
                    "basedate = {}".format(template["config"]["basedate"].isoformat())
                )
                print()
            if "repl" in template.get("config"):
                print("--- Variables replacement ---")
                for k, v in template["config"]["repl"].items():
                    print("{} = {}".format(k, v))
                print()
            return SPACE_DOMAIN, PROJECT_KEY, template

        basicConfig(level=INFO, format="%(levelname)s: %(message)s")

        SPACE_DOMAIN, PROJECT_KEY, template = prepost_check(toml.load(path_to_template))
        if is_yes("Do you want to proceed?"):
            bp = BacklogProject(SPACE_DOMAIN, PROJECT_KEY)
            bp.post_affiliated_issues(template)
        else:
            logger.info("Terminated by user input.")
        pass


def is_yes(prompt):
    return input(prompt + " (Y/n): ").lower() == "y"


if __name__ == "__main__":
    fire.Fire(BacklogProjectCLI)
