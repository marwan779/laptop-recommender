using Users.Application;
using Users.Api.Middleware;
using Users.Infrastructure;
using Users.Infrastructure.Logging;

var builder = WebApplication.CreateBuilder(args);

builder.Logging.AddGlobalLogger(builder.Configuration);

builder.Services.AddApplication();
builder.Services.AddInfrastructure(builder.Configuration);

builder.Services.AddControllers();
builder.Services.AddOpenApi();

var app = builder.Build();

app.UseMiddleware<CorrelationIdMiddleware>();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.MapControllers();

app.Run();
