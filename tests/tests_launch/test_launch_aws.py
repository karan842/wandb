import configparser
import json
import os
from unittest.mock import MagicMock


from wandb.sdk.launch.runner.aws import (
    SagemakerSubmittedRun,
    get_aws_credentials,
    get_region,
)

import sys

import boto3
import wandb
import wandb.util as util
import wandb.sdk.launch.launch as launch
import wandb.sdk.launch._project_spec as _project_spec

from .test_launch import mocked_fetchable_git_repo  # noqa: F401
from ..utils import fixture_open

import pytest


def mock_boto3_client(*args, **kwargs):
    if args[0] == "sagemaker":
        mock_sagemaker_client = MagicMock()
        mock_sagemaker_client.create_training_job.return_value = {
            "TrainingJobArn": "arn:aws:sagemaker:us-east-1:123456789012:TrainingJob/test-job-1"
        }
        mock_sagemaker_client.stop_training_job.return_value = {
            "TrainingJobArn": "arn:aws:sagemaker:us-east-1:123456789012:TrainingJob/test-job-1"
        }
        mock_sagemaker_client.describe_training_job.return_value = {
            "TrainingJobStatus": "Completed",
            "TrainingJobName": "test-job-1",
        }
        return mock_sagemaker_client
    elif args[0] == "ecr":
        ecr_client = MagicMock()
        ecr_client.get_authorization_token.return_value = {
            "authorizationData": [
                {
                    "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                }
            ]
        }
        return ecr_client
    elif args[0] == "sts":
        sts_client = MagicMock()
        sts_client.get_caller_identity.return_value = {
            "Account": "123456789012",
        }
        return sts_client


def test_launch_aws_sagemaker(
    live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch,
):
    def mock_create_metadata_file(*args, **kwargs):
        dockerfile_contents = args[4]
        expected_entrypoint = 'ENTRYPOINT ["sh", "train"]'
        assert expected_entrypoint in dockerfile_contents, dockerfile_contents
        _project_spec.create_metadata_file(*args, **kwargs)

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setattr(
        wandb.sdk.launch.docker, "create_metadata_file", mock_create_metadata_file,
    )
    monkeypatch.setattr(wandb.docker, "tag", lambda x, y: "")
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: f"The push refers to repository [{x}]"
    )
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    api = wandb.sdk.internal.internal_api.Api(
        default_settings=test_settings, load_settings=False
    )
    uri = "https://wandb.ai/mock_server_entity/test/runs/1"
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    kwargs["uri"] = uri
    kwargs["api"] = api
    run = launch.run(**kwargs)
    assert run.training_job_name == "test-job-1"


@pytest.mark.timeout(320)
def test_launch_aws_sagemaker_launch_fail(
    live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch,
):
    def mock_client_launch_fail(*args, **kwargs):
        if args[0] == "sagemaker":
            mock_sagemaker_client = MagicMock()
            mock_sagemaker_client.create_training_job.return_value = {}
            mock_sagemaker_client.stop_training_job.return_value = {
                "TrainingJobArn": "arn:aws:sagemaker:us-east-1:123456789012:TrainingJob/test-job-1"
            }
            mock_sagemaker_client.describe_training_job.return_value = {
                "TrainingJobStatus": "Completed",
                "TrainingJobName": "test-job-1",
            }
            return mock_sagemaker_client
        elif args[0] == "ecr":
            ecr_client = MagicMock()
            ecr_client.get_authorization_token.return_value = {
                "authorizationData": [
                    {
                        "proxyEndpoint": "https://123456789012.dkr.ecr.us-east-1.amazonaws.com",
                    }
                ]
            }
            return ecr_client
        elif args[0] == "sts":
            sts_client = MagicMock()
            sts_client.get_caller_identity.return_value = {
                "Account": "123456789012",
            }
            return sts_client

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(boto3, "client", mock_client_launch_fail)
    monkeypatch.setattr(wandb.docker, "tag", lambda x, y: "")
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: f"The push refers to repository [{x}]"
    )
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    api = wandb.sdk.internal.internal_api.Api(
        default_settings=test_settings, load_settings=False
    )
    uri = "https://wandb.ai/mock_server_entity/test/runs/1"
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    kwargs["uri"] = uri
    kwargs["api"] = api

    with pytest.raises(wandb.errors.LaunchError) as e_info:
        launch.run(**kwargs)
    assert "Unable to create training job" in str(e_info.value)


@pytest.mark.timeout(320)
def test_launch_aws_sagemaker_push_image_fail_none(
    live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch,
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setattr(wandb.docker, "tag", lambda x, y: "")
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    monkeypatch.setattr(wandb.docker, "push", lambda x, y: None)

    api = wandb.sdk.internal.internal_api.Api(
        default_settings=test_settings, load_settings=False
    )
    uri = "https://wandb.ai/mock_server_entity/test/runs/1"
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    kwargs["uri"] = uri
    kwargs["api"] = api

    with pytest.raises(wandb.errors.LaunchError) as e_info:
        launch.run(**kwargs)
    assert "Failed to push image to repository" in str(e_info.value)


def test_launch_aws_sagemaker_push_image_fail_err_msg(
    live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch,
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setattr(wandb.docker, "tag", lambda x, y: "")
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: "I regret to inform you, that I have failed"
    )

    api = wandb.sdk.internal.internal_api.Api(
        default_settings=test_settings, load_settings=False
    )
    uri = "https://wandb.ai/mock_server_entity/test/runs/1"
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    kwargs["uri"] = uri
    kwargs["api"] = api

    with pytest.raises(wandb.errors.LaunchError) as e_info:
        launch.run(**kwargs)
    assert "I regret to inform you, that I have failed" in str(e_info.value)


@pytest.mark.skipif(
    sys.version_info < (3, 5),
    reason="wandb launch is not available for python versions < 3.5",
)
def test_sagemaker_specified_image(
    live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch, capsys
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    api = wandb.sdk.internal.internal_api.Api(
        default_settings=test_settings, load_settings=False
    )
    uri = "https://wandb.ai/mock_server_entity/test/runs/1"
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    kwargs["uri"] = uri
    kwargs["api"] = api
    kwargs["resource_args"]["sagemaker"]["AlgorithmSpecification"][
        "TrainingImage"
    ] = "my-test_image"
    kwargs["resource_args"]["sagemaker"]["AlgorithmSpecification"][
        "TrainingInputMode"
    ] = "File"
    run = launch.run(**kwargs)
    stderr = capsys.readouterr().err
    assert (
        "Launching sagemaker job with user provided ECR image, this image will not be able to swap artifacts"
        in stderr
    )
    assert run.training_job_name == "test-job-1"


def test_aws_submitted_run_status():
    mock_sagemaker_client = MagicMock()
    mock_sagemaker_client.describe_training_job.return_value = {
        "TrainingJobStatus": "InProgress",
    }
    run = SagemakerSubmittedRun("test-job-1", mock_sagemaker_client)
    assert run.get_status().state == "running"

    mock_sagemaker_client.describe_training_job.return_value = {
        "TrainingJobStatus": "Completed",
    }
    run = SagemakerSubmittedRun("test-job-1", mock_sagemaker_client)
    assert run.get_status().state == "finished"

    mock_sagemaker_client.describe_training_job.return_value = {
        "TrainingJobStatus": "Failed",
    }
    run = SagemakerSubmittedRun("test-job-1", mock_sagemaker_client)
    assert run.get_status().state == "failed"

    mock_sagemaker_client.describe_training_job.return_value = {
        "TrainingJobStatus": "Stopped",
    }
    run = SagemakerSubmittedRun("test-job-1", mock_sagemaker_client)
    assert run.get_status().state == "finished"

    mock_sagemaker_client.describe_training_job.return_value = {
        "TrainingJobStatus": "Stopping",
    }
    run = SagemakerSubmittedRun("test-job-1", mock_sagemaker_client)
    assert run.get_status().state == "stopping"


def test_aws_submitted_run_cancel():
    mock_sagemaker_client = MagicMock()
    mock_sagemaker_client.stopping = 0

    def mock_describe_training_job(TrainingJobName):
        if mock_sagemaker_client.stopping == 1:
            mock_sagemaker_client.stopping += 1
            return {
                "TrainingJobStatus": "Stopping",
            }
        elif mock_sagemaker_client.stopping == 2:
            return {
                "TrainingJobStatus": "Stopped",
            }
        else:
            return {
                "TrainingJobStatus": "InProgress",
            }

    def mock_stop_training_job(TrainingJobName):
        mock_sagemaker_client.stopping += 1
        return {
            "TrainingJobStatus": "Stopping",
        }

    mock_sagemaker_client.describe_training_job = mock_describe_training_job
    mock_sagemaker_client.stop_training_job = mock_stop_training_job
    run = SagemakerSubmittedRun("test-job-1", mock_sagemaker_client)
    run.cancel()
    assert run._status.state == "finished"


def test_aws_submitted_run_id():
    run = SagemakerSubmittedRun("test-job-1", None)
    assert run.id == "sagemaker-test-job-1"


def test_aws_get_aws_credentials_file_success(runner, monkeypatch):
    def mock_get_creds(self, section, key):
        if key == "aws_access_key_id":
            return "test-key"
        elif key == "aws_secret_access_key":
            return "test-secret"
        else:
            return None

    monkeypatch.setattr(configparser.ConfigParser, "read", lambda x, y: {})
    monkeypatch.setattr(configparser.ConfigParser, "get", mock_get_creds)

    with runner.isolated_filesystem():
        key, secret = get_aws_credentials({})
        assert key == "test-key"
        assert secret == "test-secret"


def test_failed_aws_cred_login(
    runner, live_mock_server, monkeypatch, test_settings, mocked_fetchable_git_repo
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Failed\n"
    )
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    with runner.isolated_filesystem():
        uri = "https://wandb.ai/mock_server_entity/test/runs/1"
        api = wandb.sdk.internal.internal_api.Api(
            default_settings=test_settings, load_settings=False
        )
        kwargs["uri"] = uri
        kwargs["api"] = api

        with pytest.raises(wandb.errors.LaunchError):
            launch.run(**kwargs)


def test_aws_get_region_file_success(runner, monkeypatch):
    def mock_get_region(self, section, key):
        if key == "region":
            return "us-east-1"
        else:
            return None

    with runner.isolated_filesystem():
        monkeypatch.setattr(os.path, "exists", lambda x: True)
        monkeypatch.setattr(configparser.ConfigParser, "read", lambda x, y: {})
        monkeypatch.setattr(configparser.ConfigParser, "get", mock_get_region)
        launch_project = _project_spec.LaunchProject(
            "https://wandb.ai/mock_server_entity/test/runs/1",
            None,
            {},
            "test",
            "test",
            resource="sagemaker",
            name="test",
            docker_config={},
            git_info={},
            overrides={},
            resource_args={},
            cuda=None,
        )
        region = get_region(launch_project.resource_args)
        assert region == "us-east-1"


def test_aws_get_region_file_fail_no_section(runner, monkeypatch):
    def mock_get(x, y, z):
        raise configparser.NoSectionError("default")

    monkeypatch.setattr("os.path.exists", lambda x: True)
    monkeypatch.setattr(configparser.ConfigParser, "read", lambda x, y: {})
    monkeypatch.setattr(configparser.ConfigParser, "get", mock_get)
    with runner.isolated_filesystem():
        launch_project = _project_spec.LaunchProject(
            "https://wandb.ai/mock_server_entity/test/runs/1",
            None,
            {},
            "test",
            "test",
            resource="sagemaker",
            name="test",
            docker_config={},
            git_info={},
            overrides={},
            resource_args={},
            cuda=None,
        )
        with pytest.raises(wandb.errors.LaunchError) as e_info:
            get_region(launch_project.resource_args)
        assert (
            str(e_info.value)
            == "Unable to detemine default region from ~/.aws/config. "
            "Please specify region in resource args or specify config "
            "section as 'profile'"
        )


def test_aws_get_region_file_fail_no_file(runner, monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda x: False)
    with runner.isolated_filesystem():
        launch_project = _project_spec.LaunchProject(
            "https://wandb.ai/mock_server_entity/test/runs/1",
            None,
            {},
            "test",
            "test",
            resource="sagemaker",
            name="test",
            docker_config={},
            git_info={},
            overrides={},
            resource_args={},
            cuda=None,
        )
        with pytest.raises(wandb.errors.LaunchError) as e_info:
            get_region(launch_project.resource_args)
        assert (
            str(e_info.value)
            == "AWS region not specified and ~/.aws/config not found. Configure AWS"
        )


def test_no_sagemaker_resource_args(
    runner, live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch
):
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: f"The push refers to repository [{x}]"
    )
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    with runner.isolated_filesystem():
        uri = "https://wandb.ai/mock_server_entity/test/runs/1"
        api = wandb.sdk.internal.internal_api.Api(
            default_settings=test_settings, load_settings=False
        )
        kwargs["uri"] = uri
        kwargs["api"] = api
        kwargs["resource_args"].pop("sagemaker", None)
        with pytest.raises(wandb.errors.LaunchError) as e_info:
            launch.run(**kwargs)
        assert (
            str(e_info.value)
            == "No sagemaker args specified. Specify sagemaker args in resource_args"
        )


def test_no_OuputDataConfig(
    runner, live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch
):
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: f"The push refers to repository [{x}]"
    )
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    with runner.isolated_filesystem():
        uri = "https://wandb.ai/mock_server_entity/test/runs/1"
        api = wandb.sdk.internal.internal_api.Api(
            default_settings=test_settings, load_settings=False
        )
        kwargs["uri"] = uri
        kwargs["api"] = api
        kwargs["resource_args"]["sagemaker"].pop("OutputDataConfig", None)
        with pytest.raises(wandb.errors.LaunchError) as e_info:
            launch.run(**kwargs)
        assert (
            str(e_info.value)
            == "Sagemaker launcher requires an OutputDataConfig Sagemaker resource argument"
        )


def test_no_StoppingCondition(
    runner, live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch
):
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: f"The push refers to repository [{x}]"
    )
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    with runner.isolated_filesystem():
        uri = "https://wandb.ai/mock_server_entity/test/runs/1"
        api = wandb.sdk.internal.internal_api.Api(
            default_settings=test_settings, load_settings=False
        )
        kwargs["uri"] = uri
        kwargs["api"] = api
        kwargs["resource_args"]["sagemaker"].pop("StoppingCondition", None)

        with pytest.raises(wandb.errors.LaunchError) as e_info:
            launch.run(**kwargs)
        assert (
            str(e_info.value)
            == "Sagemaker launcher requires a StoppingCondition Sagemaker resource argument"
        )


def test_no_ResourceConfig(
    runner, live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch
):
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: f"The push refers to repository [{x}]"
    )
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    with runner.isolated_filesystem():
        uri = "https://wandb.ai/mock_server_entity/test/runs/1"
        api = wandb.sdk.internal.internal_api.Api(
            default_settings=test_settings, load_settings=False
        )
        kwargs["uri"] = uri
        kwargs["api"] = api
        kwargs["resource_args"]["sagemaker"].pop("ResourceConfig", None)

        with pytest.raises(wandb.errors.LaunchError) as e_info:
            launch.run(**kwargs)
        assert (
            str(e_info.value)
            == "Sagemaker launcher requires a ResourceConfig Sagemaker resource argument"
        )


def test_no_RoleARN(
    runner, live_mock_server, test_settings, mocked_fetchable_git_repo, monkeypatch
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(boto3, "client", mock_boto3_client)
    monkeypatch.setattr(
        wandb.sdk.launch.runner.aws, "aws_ecr_login", lambda x, y: "Login Succeeded\n"
    )
    monkeypatch.setattr(
        wandb.docker, "push", lambda x, y: f"The push refers to repository [{x}]"
    )
    kwargs = json.loads(fixture_open("launch/launch_sagemaker_config.json").read())
    with runner.isolated_filesystem():
        uri = "https://wandb.ai/mock_server_entity/test/runs/1"
        api = wandb.sdk.internal.internal_api.Api(
            default_settings=test_settings, load_settings=False
        )
        kwargs["uri"] = uri
        kwargs["api"] = api
        kwargs["resource_args"]["sagemaker"].pop("RoleArn", None)

        with pytest.raises(wandb.errors.LaunchError) as e_info:
            launch.run(**kwargs)
        assert (
            str(e_info.value)
            == "AWS sagemaker require a string RoleArn set this by adding a `RoleArn` key to the sagemaker"
            "field of resource_args"
        )