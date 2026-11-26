using Microsoft.AspNetCore.Mvc;
using Users.Application.Common.Interfaces;

namespace Users.Api.Controllers;

[ApiController]
[Route("health")]
public sealed class HealthController(IHealthCheckService healthCheckService) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> Get(CancellationToken cancellationToken)
    {
        var dbHealthy = await healthCheckService.CanConnectToDatabaseAsync(cancellationToken);
        var payload = new
        {
            service = "users-service",
            status = dbHealthy ? "ok" : "degraded",
            database = dbHealthy ? "ok" : "unreachable",
        };

        return dbHealthy
            ? Ok(payload)
            : StatusCode(StatusCodes.Status503ServiceUnavailable, payload);
    }
}
