"""Split contributors table into core identity and platform data

Revision ID: 38
Revises: 37
Create Date: 2026-01-11 12:00:00.000000

This migration addresses issue #3363 by splitting the contributors table into two tables:
1. contributors - Core identity fields (email, name, login, canonical email)
2. contributor_platform_data - Platform-specific fields (gh_*, gl_* columns)

This eliminates data contention between GitHub/GitLab API tasks (core) and 
Git commit tasks (facade), and prevents partial NULL data when only one process runs.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '38'
down_revision = '37'
branch_labels = None
depends_on = None


def upgrade():
    """Split contributors table into core identity and platform data tables."""
    
    conn = op.get_bind()
    
    # Step 1: Create the new contributor_platform_data table
    print("Creating contributor_platform_data table...")
    op.create_table(
        'contributor_platform_data',
        sa.Column('platform_data_id', postgresql.UUID(as_uuid=True), 
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('cntrb_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        
        # GitHub-specific fields
        sa.Column('gh_user_id', sa.BigInteger(), nullable=True),
        sa.Column('gh_login', sa.String(), nullable=True),
        sa.Column('gh_url', sa.String(), nullable=True),
        sa.Column('gh_html_url', sa.String(), nullable=True),
        sa.Column('gh_node_id', sa.String(), nullable=True),
        sa.Column('gh_avatar_url', sa.String(), nullable=True),
        sa.Column('gh_gravatar_id', sa.String(), nullable=True),
        sa.Column('gh_followers_url', sa.String(), nullable=True),
        sa.Column('gh_following_url', sa.String(), nullable=True),
        sa.Column('gh_gists_url', sa.String(), nullable=True),
        sa.Column('gh_starred_url', sa.String(), nullable=True),
        sa.Column('gh_subscriptions_url', sa.String(), nullable=True),
        sa.Column('gh_organizations_url', sa.String(), nullable=True),
        sa.Column('gh_repos_url', sa.String(), nullable=True),
        sa.Column('gh_events_url', sa.String(), nullable=True),
        sa.Column('gh_received_events_url', sa.String(), nullable=True),
        sa.Column('gh_type', sa.String(), nullable=True),
        sa.Column('gh_site_admin', sa.String(), nullable=True),
        
        # GitLab-specific fields
        sa.Column('gl_id', sa.BigInteger(), nullable=True),
        sa.Column('gl_username', sa.String(), nullable=True),
        sa.Column('gl_full_name', sa.String(), nullable=True),
        sa.Column('gl_web_url', sa.String(), nullable=True),
        sa.Column('gl_avatar_url', sa.String(), nullable=True),
        sa.Column('gl_state', sa.String(), nullable=True),
        
        # Audit fields
        sa.Column('tool_source', sa.String(), nullable=True),
        sa.Column('tool_version', sa.String(), nullable=True),
        sa.Column('data_source', sa.String(), nullable=True),
        sa.Column('data_collection_date', postgresql.TIMESTAMP(precision=0), 
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        
        # Primary key
        sa.PrimaryKeyConstraint('platform_data_id'),
        
        # Foreign key
        sa.ForeignKeyConstraint(['cntrb_id'], ['augur_data.contributors.cntrb_id'], 
                                name='cpd_cntrb_id_fk', ondelete='CASCADE'),
        
        # Unique constraints (moved from contributors table)
        sa.UniqueConstraint('cntrb_id', 'platform', name='unique_cntrb_platform'),
        sa.UniqueConstraint('gh_login', name='GH-UNIQUE-C', 
                          deferrable=True, initially='DEFERRED'),
        sa.UniqueConstraint('gl_id', name='GL-UNIQUE-B', 
                          deferrable=True, initially='DEFERRED'),
        sa.UniqueConstraint('gl_username', name='GL-UNIQUE-C', 
                          deferrable=True, initially='DEFERRED'),
        
        schema='augur_data',
        comment='Platform-specific contributor data from GitHub, GitLab, etc.'
    )
    
    # Step 2: Create indexes on the new table
    print("Creating indexes on contributor_platform_data...")
    conn.execute(text("""
        CREATE INDEX "gh_login_idx" ON "augur_data"."contributor_platform_data" 
        USING btree ("gh_login" ASC NULLS FIRST);
        
        CREATE INDEX "cpd_cntrb_id_idx" ON "augur_data"."contributor_platform_data" ("cntrb_id");
        CREATE INDEX "cpd_gh_user_id_idx" ON "augur_data"."contributor_platform_data" ("gh_user_id");
        CREATE INDEX "cpd_gl_id_idx" ON "augur_data"."contributor_platform_data" ("gl_id");
        CREATE INDEX "cpd_platform_idx" ON "augur_data"."contributor_platform_data" ("platform");
    """))
    
    # Step 3: Migrate GitHub platform data
    print("Migrating GitHub platform data...")
    conn.execute(text("""
        INSERT INTO augur_data.contributor_platform_data (
            cntrb_id, platform, 
            gh_user_id, gh_login, gh_url, gh_html_url, gh_node_id, gh_avatar_url, 
            gh_gravatar_id, gh_followers_url, gh_following_url, gh_gists_url, 
            gh_starred_url, gh_subscriptions_url, gh_organizations_url, gh_repos_url, 
            gh_events_url, gh_received_events_url, gh_type, gh_site_admin,
            tool_source, tool_version, data_source, data_collection_date
        )
        SELECT 
            cntrb_id, 'github',
            gh_user_id, gh_login, gh_url, gh_html_url, gh_node_id, gh_avatar_url,
            gh_gravatar_id, gh_followers_url, gh_following_url, gh_gists_url,
            gh_starred_url, gh_subscriptions_url, gh_organizations_url, gh_repos_url,
            gh_events_url, gh_received_events_url, gh_type, gh_site_admin,
            tool_source, tool_version, data_source, data_collection_date
        FROM augur_data.contributors
        WHERE gh_user_id IS NOT NULL;
    """))
    
    # Step 4: Migrate GitLab platform data
    print("Migrating GitLab platform data...")
    conn.execute(text("""
        INSERT INTO augur_data.contributor_platform_data (
            cntrb_id, platform,
            gl_id, gl_username, gl_full_name, gl_web_url, gl_avatar_url, gl_state,
            tool_source, tool_version, data_source, data_collection_date
        )
        SELECT 
            cntrb_id, 'gitlab',
            gl_id, gl_username, gl_full_name, gl_web_url, gl_avatar_url, gl_state,
            tool_source, tool_version, data_source, data_collection_date
        FROM augur_data.contributors
        WHERE gl_id IS NOT NULL;
    """))
    
    # Step 5: Verify migration (get counts for logging)
    result = conn.execute(text("""
        SELECT 
            (SELECT COUNT(*) FROM augur_data.contributors) as total_contributors,
            (SELECT COUNT(*) FROM augur_data.contributor_platform_data WHERE platform = 'github') as github_count,
            (SELECT COUNT(*) FROM augur_data.contributor_platform_data WHERE platform = 'gitlab') as gitlab_count;
    """))
    row = result.fetchone()
    print(f"Migration stats: {row[0]} contributors, {row[1]} GitHub, {row[2]} GitLab platform records")
    
    # Step 6: Drop the unique constraints from contributors table (now in platform_data)
    print("Dropping old unique constraints from contributors table...")
    conn.execute(text("""
        ALTER TABLE augur_data.contributors 
        DROP CONSTRAINT IF EXISTS "GH-UNIQUE-C";
        
        ALTER TABLE augur_data.contributors 
        DROP CONSTRAINT IF EXISTS "GL-UNIQUE-B";
        
        ALTER TABLE augur_data.contributors 
        DROP CONSTRAINT IF EXISTS "GL-UNIQUE-C";
    """))
    
    # Step 7: Drop the gh_login index from contributors table (now in platform_data)
    print("Dropping gh_login index from contributors table...")
    conn.execute(text("""
        DROP INDEX IF EXISTS augur_data."gh_login";
    """))
    
    # Step 8: Drop platform-specific columns from contributors table
    print("Dropping platform-specific columns from contributors table...")
    op.drop_column('contributors', 'gh_user_id', schema='augur_data')
    op.drop_column('contributors', 'gh_login', schema='augur_data')
    op.drop_column('contributors', 'gh_url', schema='augur_data')
    op.drop_column('contributors', 'gh_html_url', schema='augur_data')
    op.drop_column('contributors', 'gh_node_id', schema='augur_data')
    op.drop_column('contributors', 'gh_avatar_url', schema='augur_data')
    op.drop_column('contributors', 'gh_gravatar_id', schema='augur_data')
    op.drop_column('contributors', 'gh_followers_url', schema='augur_data')
    op.drop_column('contributors', 'gh_following_url', schema='augur_data')
    op.drop_column('contributors', 'gh_gists_url', schema='augur_data')
    op.drop_column('contributors', 'gh_starred_url', schema='augur_data')
    op.drop_column('contributors', 'gh_subscriptions_url', schema='augur_data')
    op.drop_column('contributors', 'gh_organizations_url', schema='augur_data')
    op.drop_column('contributors', 'gh_repos_url', schema='augur_data')
    op.drop_column('contributors', 'gh_events_url', schema='augur_data')
    op.drop_column('contributors', 'gh_received_events_url', schema='augur_data')
    op.drop_column('contributors', 'gh_type', schema='augur_data')
    op.drop_column('contributors', 'gh_site_admin', schema='augur_data')
    
    op.drop_column('contributors', 'gl_id', schema='augur_data')
    op.drop_column('contributors', 'gl_username', schema='augur_data')
    op.drop_column('contributors', 'gl_full_name', schema='augur_data')
    op.drop_column('contributors', 'gl_web_url', schema='augur_data')
    op.drop_column('contributors', 'gl_avatar_url', schema='augur_data')
    op.drop_column('contributors', 'gl_state', schema='augur_data')
    
    print("Migration completed successfully!")


def downgrade():
    """Restore the original contributors table structure."""
    
    conn = op.get_bind()
    
    print("Rolling back: Adding platform-specific columns back to contributors table...")
    
    # Step 1: Add back all the platform-specific columns to contributors
    # GitHub fields
    op.add_column('contributors', sa.Column('gh_user_id', sa.BigInteger(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_login', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_html_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_node_id', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_avatar_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_gravatar_id', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_followers_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_following_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_gists_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_starred_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_subscriptions_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_organizations_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_repos_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_events_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_received_events_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_type', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gh_site_admin', sa.String(), nullable=True), schema='augur_data')
    
    # GitLab fields
    op.add_column('contributors', sa.Column('gl_id', sa.BigInteger(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gl_username', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gl_full_name', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gl_web_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gl_avatar_url', sa.String(), nullable=True), schema='augur_data')
    op.add_column('contributors', sa.Column('gl_state', sa.String(), nullable=True), schema='augur_data')
    
    # Step 2: Copy data back from contributor_platform_data to contributors (GitHub)
    print("Restoring GitHub data to contributors table...")
    conn.execute(text("""
        UPDATE augur_data.contributors c
        SET 
            gh_user_id = cpd.gh_user_id,
            gh_login = cpd.gh_login,
            gh_url = cpd.gh_url,
            gh_html_url = cpd.gh_html_url,
            gh_node_id = cpd.gh_node_id,
            gh_avatar_url = cpd.gh_avatar_url,
            gh_gravatar_id = cpd.gh_gravatar_id,
            gh_followers_url = cpd.gh_followers_url,
            gh_following_url = cpd.gh_following_url,
            gh_gists_url = cpd.gh_gists_url,
            gh_starred_url = cpd.gh_starred_url,
            gh_subscriptions_url = cpd.gh_subscriptions_url,
            gh_organizations_url = cpd.gh_organizations_url,
            gh_repos_url = cpd.gh_repos_url,
            gh_events_url = cpd.gh_events_url,
            gh_received_events_url = cpd.gh_received_events_url,
            gh_type = cpd.gh_type,
            gh_site_admin = cpd.gh_site_admin
        FROM augur_data.contributor_platform_data cpd
        WHERE c.cntrb_id = cpd.cntrb_id 
        AND cpd.platform = 'github';
    """))
    
    # Step 3: Copy data back from contributor_platform_data to contributors (GitLab)
    print("Restoring GitLab data to contributors table...")
    conn.execute(text("""
        UPDATE augur_data.contributors c
        SET 
            gl_id = cpd.gl_id,
            gl_username = cpd.gl_username,
            gl_full_name = cpd.gl_full_name,
            gl_web_url = cpd.gl_web_url,
            gl_avatar_url = cpd.gl_avatar_url,
            gl_state = cpd.gl_state
        FROM augur_data.contributor_platform_data cpd
        WHERE c.cntrb_id = cpd.cntrb_id 
        AND cpd.platform = 'gitlab';
    """))
    
    # Step 4: Restore unique constraints on contributors table
    print("Restoring unique constraints on contributors table...")
    conn.execute(text("""
        ALTER TABLE augur_data.contributors 
        ADD CONSTRAINT "GH-UNIQUE-C" UNIQUE (gh_login) DEFERRABLE INITIALLY DEFERRED;
        
        ALTER TABLE augur_data.contributors 
        ADD CONSTRAINT "GL-UNIQUE-B" UNIQUE (gl_id) DEFERRABLE INITIALLY DEFERRED;
        
        ALTER TABLE augur_data.contributors 
        ADD CONSTRAINT "GL-UNIQUE-C" UNIQUE (gl_username) DEFERRABLE INITIALLY DEFERRED;
    """))
    
    # Step 5: Restore gh_login index on contributors table
    print("Restoring gh_login index on contributors table...")
    conn.execute(text("""
        CREATE INDEX "gh_login" ON "augur_data"."contributors" 
        USING btree ("gh_login" ASC NULLS FIRST);
    """))
    
    # Step 6: Drop contributor_platform_data table
    print("Dropping contributor_platform_data table...")
    op.drop_table('contributor_platform_data', schema='augur_data')
    
    print("Rollback completed successfully!")
