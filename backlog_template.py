from datetime import datetime
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

    def post_issue(self, **kwargs):
        return self.post(
            end_point=self.base_url + "issues",
            data={
                "projectId": self.project_id,
                "summary": kwargs["summary"],
                "issueTypeId": kwargs["issueTypeId"],
                "priorityId": kwargs["priorityId"],
                "parentIssueId": kwargs.get("parentIssueId"),
                "description": kwargs.get("description"),
                "dueDate": kwargs.get("dueDate"),
                "versionId[]": kwargs.get("versionId"),
                "milestoneId[]": kwargs.get("milestoneId"),
                "assigneeId": kwargs.get("assigneeId"),
            },
            params={"apiKey": self.api_key},
        )

    def post_issue_by_template(self, template):
        return self.post_issue(
            summary=template["summary"],
            issueTypeId=self.pj_issue_types[template["issueType"]],
            priorityId=self.priorities[template["priority"]],
            parentIssueId=template.get("parentIssueId"),
            description=template.get("description"),
            dueDate=template.get("dueDate"),
            versionId=self.pj_versions.get(template.get("version")),
            milestoneId=self.pj_versions.get(template.get("milestone")),
            assigneeId=self.pj_users.get(template.get("assignee")),
        )

    def post_affiliated_issues_by_template(self, template):
        def replace(dic):
            return {k: v.format(**repl) for k, v in dic.items()}

        repl = template.pop("repl", {})
        parent = template["issue"]
        children = parent.pop("children", [])
        # replace by repl(dict)
        parent = replace(parent)
        children = [replace(child) for child in children]
        # template validation
        self._validate_template(parent)
        [self._validate_template(child) for child in children]

        r = self.post_issue_by_template(parent).json()
        logger.info(
            "\nPosted an issue -> {} '{}'.".format(r["issueKey"], parent["summary"])
        )
        parentIssueId = r["id"]
        for child in children:
            # append parentIssueId to child then post
            child.update({"parentIssueId": parentIssueId})
            rc = self.post_issue_by_template(child).json()
            logger.info(
                "\nPosted a child issue of {} -> {} '{}'.".format(
                    r["issueKey"], rc["issueKey"], child["summary"]
                )
            )

    def _validate_template(self, template):
        # validate if the template contains all mandatory keys
        mandatory_keys = ("summary", "issueType", "priority")
        for k in mandatory_keys:
            assert k in template, "Template is missing a mandatory key '{}'".format(k)

        # validate if KeyError does not occur
        substitue_keys = {
            "priority": "priorities",
            "issueType": "pj_issue_types",
            "version": "pj_versions",
            "milestone": "pj_versions",
            "assignee": "pj_users",
        }
        for k, v in substitue_keys.items():
            if k not in template:
                continue
            assert template[k] in getattr(
                self, v
            ), "'{}' is not a valid key for '{}'".format(template[k], k)

        # validate date format
        date_keys = ("dueDate",)
        for k in date_keys:
            if k not in template:
                continue
            try:
                datetime.strptime(template[k], "%Y-%m-%d")
            except ValueError:
                raise ValueError("Incorrect data format, should be yyyy-MM-dd")


if __name__ == "__main__":
    from argparse import ArgumentParser
    from sys import exit

    basicConfig(level=INFO, format="%(levelname)s %(asctime)s: %(message)s")

    parser = ArgumentParser("Register affliated issues to Backlog project.")
    parser.add_argument("path_to_template", help="Path to template file (toml).")
    args = parser.parse_args()
    template = toml.load(args.path_to_template)

    # confirmation of variable replacement
    if "repl" in template:
        logger.info("--- Variables in template will be replaced as shown below. ---")
        for k, v in template["repl"].items():
            logger.info("{{{}}} = '{}'".format(k, v))
        if input("Do you want to proceed? (Y/n): ").lower() != "y":
            logger.info("--- Terminated by user input. ---")
            exit()

    bp = BacklogProject.by_config()
    bp.post_affiliated_issues_by_template(template)
