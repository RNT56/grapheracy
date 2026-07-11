from fastapi import FastAPI
from fastapi.routing import APIRoute


def install_v1_compatibility_aliases(app: FastAPI) -> None:
    legacy_routes = [
        route
        for route in list(app.routes)
        if isinstance(route, APIRoute)
        and not route.path.startswith("/api/v1")
        and route.path not in {"/health", "/version"}
    ]
    for route in legacy_routes:
        app.add_api_route(
            f"/api/v1{route.path}",
            route.endpoint,
            methods=route.methods,
            response_model=route.response_model,
            status_code=route.status_code,
            responses=route.responses,
            response_class=route.response_class,
            tags=["Graphview V1 Compatibility"],
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
            response_model_exclude_unset=route.response_model_exclude_unset,
            response_model_exclude_defaults=route.response_model_exclude_defaults,
            response_model_exclude_none=route.response_model_exclude_none,
            deprecated=False,
            openapi_extra=route.openapi_extra,
            name=f"v1-{route.name}",
        )
