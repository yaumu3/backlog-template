from datetime import datetime, timedelta
from logging import INFO, basicConfig, getLogger
from pathlib import Path

import requests
import toml

logger = getLogger(__name__)


class BaseAPI:
    def get(self, end_point, params={}):
        r = requests.get(end_point, params=params)
        r.raise_for_status()
        return r

    def post(self, end_point, data, params={}):
        r = requests.post(end_point, data, params=params)
        r.raise_for_status()
        return r


class BacklogProject(BaseAPI):
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

    def __init__(self, api_key, space_domain, project_key):
        def index(response, key="name", value="id"):
            return {d[key]: d[value] for d in response.json()}

        self.api_key = api_key
        self.base_url = "https://" + space_domain + "/api/v2/"
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

    @classmethod
    def by_config(cls, path=None):
        if path is None:
            path = Path(__file__).resolve().parent.joinpath("backlog_template.toml")
        config = toml.load(path)
        b = config["backlog_template"]
        return cls(b["API_KEY"], b["SPACE_DOMAIN"], b["PROJECT_KEY"])

    def get_prop(self, property_name):
        return self.get(
            end_point=self.base_url + property_name, params={"apiKey": self.api_key},
        )

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
            self._validate_issue(parent)
            r = self.post_issue(parent).json()
            logger.info("Posted '{} {}'.".format(r["issueKey"], parent["summary"]))
            parentIssueId = r["id"]

            children = [convert_date_by_delta(child) for child in children]
            children = [replace_curly_braces(child) for child in children]
            [self._validate_issue(child) for child in children]
            for child in children:
                child.update({"parentIssueId": parentIssueId})
                rc = self.post_issue(child).json()
                logger.info(
                    "Posted (child issue of {}) '{} {}'.".format(
                        r["issueKey"], rc["issueKey"], child["summary"]
                    )
                )

    def _validate_issue(self, issue):
        for k in self.mandatory_keys:
            assert k in issue, "Template is missing a mandatory key '{}'".format(k)

        for k, v in self.substituted_keys.items():
            if k not in issue:
                continue
            assert issue[k] in getattr(
                self, v
            ), "'{}' is not a valid key for '{}'".format(issue[k], k)


if __name__ == "__main__":
    from argparse import ArgumentParser

    def do_confirm_exec(template):
        # confirmation to let user be notified of unintentionally unchanged values
        if "basedate" in template.get("config"):
            print("--- Base date-time ---")
            print("basedate = {}".format(template["config"]["basedate"].isoformat()))
            print()
        if "repl" in template.get("config"):
            print("--- Variables replacement ---")
            for k, v in template["config"]["repl"].items():
                print("{} = {}".format(k, v))
            print()
        return input("Do you want to proceed? (Y/n): ").lower() == "y"

    parser = ArgumentParser("Register affliated issues to Backlog project.")
    parser.add_argument("path_to_template", help="Path to template file (toml).")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    template = toml.load(args.path_to_template)

    if args.verbose:
        basicConfig(level=INFO, format="%(levelname)s: %(message)s")

    if do_confirm_exec(template):
        bp = BacklogProject.by_config()
        bp.post_affiliated_issues(template)
    else:
        logger.info("Terminated by user input.")
