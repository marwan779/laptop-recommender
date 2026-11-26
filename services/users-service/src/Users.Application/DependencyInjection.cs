using Microsoft.Extensions.DependencyInjection;
using Users.Application.Features.Auth.Services;

namespace Users.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        services.AddScoped<IAuthService, AuthService>();
        return services;
    }
}
