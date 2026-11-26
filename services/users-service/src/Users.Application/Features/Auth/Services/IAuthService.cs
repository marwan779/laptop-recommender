using Users.Application.Common.Models;
using Users.Application.Features.Auth.DTOs;

namespace Users.Application.Features.Auth.Services;

public interface IAuthService
{
    Task<Result<AuthResponse>> RegisterAsync(RegisterRequest request, CancellationToken cancellationToken = default);
    Task<Result<AuthResponse>> LoginAsync(LoginRequest request, CancellationToken cancellationToken = default);
    Task<Result<AuthResponse>> RefreshAsync(RefreshTokenRequest request, CancellationToken cancellationToken = default);
    Task<Result> LogoutAsync(RefreshTokenRequest request, CancellationToken cancellationToken = default);
    Task<Result<UserProfileResponse>> GetProfileAsync(Guid userId, CancellationToken cancellationToken = default);
}
