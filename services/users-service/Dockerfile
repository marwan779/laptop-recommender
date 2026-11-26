FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

COPY UsersService.slnx ./
COPY src/Users.Domain/Users.Domain.csproj src/Users.Domain/
COPY src/Users.Application/Users.Application.csproj src/Users.Application/
COPY src/Users.Infrastructure/Users.Infrastructure.csproj src/Users.Infrastructure/
COPY src/Users.Api/Users.Api.csproj src/Users.Api/
COPY tests/Users.Domain.UnitTests/Users.Domain.UnitTests.csproj tests/Users.Domain.UnitTests/
RUN dotnet restore

COPY . .
RUN dotnet publish src/Users.Api/Users.Api.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
ENV ASPNETCORE_URLS=http://+:8080 \
    ASPNETCORE_ENVIRONMENT=Production

COPY --from=build /app/publish .
EXPOSE 8080

ENTRYPOINT ["dotnet", "Users.Api.dll"]
