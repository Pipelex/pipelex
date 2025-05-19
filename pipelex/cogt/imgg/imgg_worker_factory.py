# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pipelex.cogt.exceptions import CogtError, MissingDependencyError
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_platform import ImggPlatform
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.plugin_manager import PluginHandle
from pipelex.hub import get_plugin_manager, get_secret
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError


class FalCredentialsError(CogtError):
    pass


class ImggWorkerFactory:
    def make_imgg_worker(
        self,
        imgg_engine: ImggEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ) -> ImggWorkerAbstract:
        imgg_sdk_handle = PluginHandle.get_for_imgg_engine(imgg_platform=imgg_engine.imgg_platform)
        plugin_manager = get_plugin_manager()
        imgg_worker: ImggWorkerAbstract
        match imgg_engine.imgg_platform:
            case ImggPlatform.FAL_AI:
                try:
                    fal_api_key = get_secret(secret_id="FAL_API_KEY")
                except SecretNotFoundError as exc:
                    raise FalCredentialsError("FAL_API_KEY not found") from exc

                try:
                    from fal_client import AsyncClient as FalAsyncClient
                except ImportError as exc:
                    raise MissingDependencyError(
                        "fal-client", "fal", "The fal-client SDK is required to use FAL models (generation of images)."
                    ) from exc

                from pipelex.cogt.fal.fal_imgg_worker import FalImggWorker

                imgg_sdk_instance = plugin_manager.get_imgg_sdk_instance(imgg_sdk_handle=imgg_sdk_handle) or plugin_manager.set_imgg_sdk_instance(
                    imgg_sdk_handle=imgg_sdk_handle,
                    imgg_sdk_instance=FalAsyncClient(key=fal_api_key),
                )

                imgg_worker = FalImggWorker(
                    sdk_instance=imgg_sdk_instance,
                    imgg_engine=imgg_engine,
                    report_delegate=report_delegate,
                )

        return imgg_worker
