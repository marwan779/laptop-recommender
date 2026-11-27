using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace Users.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddWishlistItems : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "wishlist_items",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    user_id = table.Column<Guid>(type: "uuid", nullable: false),
                    canonical_id = table.Column<string>(type: "character varying(160)", maxLength: 160, nullable: false),
                    title_snapshot = table.Column<string>(type: "character varying(300)", maxLength: 300, nullable: false),
                    thumbnail_url_snapshot = table.Column<string>(type: "text", nullable: true),
                    added_price_egp = table.Column<decimal>(type: "numeric(12,2)", nullable: false),
                    last_notified_price_egp = table.Column<decimal>(type: "numeric(12,2)", nullable: true),
                    target_price_egp = table.Column<decimal>(type: "numeric(12,2)", nullable: true),
                    notify_on_price_drop = table.Column<bool>(type: "boolean", nullable: false, defaultValue: true),
                    notify_on_any_change = table.Column<bool>(type: "boolean", nullable: false, defaultValue: false),
                    notify_on_restock = table.Column<bool>(type: "boolean", nullable: false, defaultValue: true),
                    created_at_utc = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    updated_at_utc = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_wishlist_items", x => x.id);
                    table.ForeignKey(
                        name: "FK_wishlist_items_users_user_id",
                        column: x => x.user_id,
                        principalTable: "users",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_wishlist_items_canonical_id",
                table: "wishlist_items",
                column: "canonical_id");

            migrationBuilder.CreateIndex(
                name: "IX_wishlist_items_user_id_canonical_id",
                table: "wishlist_items",
                columns: new[] { "user_id", "canonical_id" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "wishlist_items");
        }
    }
}
