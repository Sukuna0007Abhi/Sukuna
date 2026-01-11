# Issue #3363: Code Locations Requiring Updates

## Overview
This document lists all code locations that need to be updated to support the split contributors table structure.

---

## 1. SQLAlchemy Models

### `/workspaces/augur/augur/application/db/models/augur_data.py`

#### A. Create New Model: `ContributorPlatformData`
**Location**: After the `Contributor` class (around line 270)

**Action**: Add new model class

```python
class ContributorPlatformData(Base):
    __tablename__ = "contributor_platform_data"
    __table_args__ = (
        UniqueConstraint('cntrb_id', 'platform', name='unique_cntrb_platform'),
        UniqueConstraint('gh_login', name='GH-UNIQUE-C', initially="DEFERRED", deferrable=True),
        UniqueConstraint('gl_id', name='GL-UNIQUE-B', initially="DEFERRED", deferrable=True),
        UniqueConstraint('gl_username', name='GL-UNIQUE-C', initially="DEFERRED", deferrable=True),
        Index("gh_login_idx", "gh_login"),
        Index("cpd_cntrb_id_idx", "cntrb_id"),
        Index("cpd_gh_user_id_idx", "gh_user_id"),
        Index("cpd_gl_id_idx", "gl_id"),
        Index("cpd_platform_idx", "platform"),
        {"schema": "augur_data", "comment": "Platform-specific contributor data"}
    )
    
    platform_data_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    cntrb_id = Column(UUID(as_uuid=True), ForeignKey('augur_data.contributors.cntrb_id', ondelete='CASCADE'), nullable=False)
    platform = Column(String, nullable=False)
    
    # GitHub fields
    gh_user_id = Column(BigInteger)
    gh_login = Column(String)
    gh_url = Column(String)
    gh_html_url = Column(String)
    gh_node_id = Column(String)
    gh_avatar_url = Column(String)
    gh_gravatar_id = Column(String)
    gh_followers_url = Column(String)
    gh_following_url = Column(String)
    gh_gists_url = Column(String)
    gh_starred_url = Column(String)
    gh_subscriptions_url = Column(String)
    gh_organizations_url = Column(String)
    gh_repos_url = Column(String)
    gh_events_url = Column(String)
    gh_received_events_url = Column(String)
    gh_type = Column(String)
    gh_site_admin = Column(String)
    
    # GitLab fields
    gl_id = Column(BigInteger)
    gl_username = Column(String)
    gl_full_name = Column(String)
    gl_web_url = Column(String)
    gl_avatar_url = Column(String)
    gl_state = Column(String)
    
    # Audit fields
    tool_source = Column(String)
    tool_version = Column(String)
    data_source = Column(String)
    data_collection_date = Column(TIMESTAMP(precision=0), server_default=text("CURRENT_TIMESTAMP"))
    
    # Relationship
    contributor = relationship("Contributor", back_populates="platform_data")
```

#### B. Update `Contributor` Model
**Location**: Lines 146-270

**Actions**:
1. **Remove columns**: All `gh_*` and `gl_*` columns
2. **Remove constraints**: `GH-UNIQUE-C`, `GL-UNIQUE-B`, `GL-UNIQUE-C`
3. **Add relationship**: `platform_data = relationship("ContributorPlatformData", back_populates="contributor", lazy='select')`

**Modified Fields** (keep these):
- `cntrb_id`, `cntrb_login`, `cntrb_email`, `cntrb_full_name`
- `cntrb_company`, `cntrb_created_at`, `cntrb_type`
- `cntrb_fake`, `cntrb_deleted`
- `cntrb_long`, `cntrb_lat`, `cntrb_country_code`, `cntrb_state`, `cntrb_city`, `cntrb_location`
- `cntrb_canonical`, `cntrb_last_used`
- `tool_source`, `tool_version`, `data_source`, `data_collection_date`

---

## 2. Data Parsing Functions

### `/workspaces/augur/augur/application/db/data_parse.py`

#### A. `extract_needed_contributor_data()` - Line 649
**Current**: Returns single dict with all fields
**New**: Returns tuple of (core_data, platform_data)

```python
def extract_needed_contributor_data(contributor, tool_source, tool_version, data_source):
    if not contributor:
        return None, None
    
    cntrb_id = GithubUUID()
    cntrb_id["user"] = contributor["id"]
    uuid = cntrb_id.to_UUID()
    
    # Core contributor data (for contributors table)
    core_data = {
        "cntrb_id": uuid,
        "cntrb_login": contributor['login'],
        "cntrb_created_at": contributor['created_at'] if 'created_at' in contributor else None,
        "cntrb_email": contributor['email'] if 'email' in contributor else None,
        "cntrb_company": contributor['company'] if 'company' in contributor else None,
        "cntrb_location": contributor['location'] if 'location' in contributor else None,
        "cntrb_canonical": contributor['email'] if 'email' in contributor else None,
        "cntrb_last_used": None if 'updated_at' not in contributor else contributor['updated_at'],
        "cntrb_full_name": None if 'name' not in contributor else contributor['name'],
        "tool_source": tool_source,
        "tool_version": tool_version,
        "data_source": data_source
    }
    
    # Platform-specific data (for contributor_platform_data table)
    platform_data = {
        "cntrb_id": uuid,
        "platform": "github",
        "gh_user_id": contributor['id'],
        "gh_login": str(contributor['login']),
        "gh_url": contributor['url'],
        "gh_html_url": contributor['html_url'],
        "gh_node_id": contributor['node_id'],
        "gh_avatar_url": contributor['avatar_url'],
        "gh_gravatar_id": contributor['gravatar_id'],
        "gh_followers_url": contributor['followers_url'],
        "gh_following_url": contributor['following_url'],
        "gh_gists_url": contributor['gists_url'],
        "gh_starred_url": contributor['starred_url'],
        "gh_subscriptions_url": contributor['subscriptions_url'],
        "gh_organizations_url": contributor['organizations_url'],
        "gh_repos_url": contributor['repos_url'],
        "gh_events_url": contributor['events_url'],
        "gh_received_events_url": contributor['received_events_url'],
        "gh_type": contributor['type'],
        "gh_site_admin": contributor['site_admin'],
        "tool_source": tool_source,
        "tool_version": tool_version,
        "data_source": data_source
    }
    
    return core_data, platform_data
```

#### B. `extract_needed_gitlab_contributor_data()` - Line 693
**Current**: Returns single dict with all fields
**New**: Returns tuple of (core_data, platform_data)

Similar transformation as above but for GitLab.

---

## 3. Database Library Functions

### `/workspaces/augur/augur/application/db/lib.py`

#### A. `batch_insert_contributors()` - Need to locate exact line
**Current**: Inserts contributors with platform fields
**New**: Insert into both `contributors` and `contributor_platform_data` tables

```python
def batch_insert_contributors(contributors_data: List[Tuple[dict, dict]], logger):
    """
    Insert contributors and their platform data
    
    Args:
        contributors_data: List of tuples (core_data, platform_data) or dicts (backward compat)
    """
    core_contributors = []
    platform_data_list = []
    
    for item in contributors_data:
        # Handle both new tuple format and old dict format for backward compatibility
        if isinstance(item, tuple):
            core_data, platform_data = item
        else:
            # Old format - extract platform data from dict
            core_data, platform_data = split_contributor_dict(item)
        
        if core_data:
            core_contributors.append(core_data)
        if platform_data:
            platform_data_list.append(platform_data)
    
    # Insert core contributors
    if core_contributors:
        bulk_insert_dicts(logger, core_contributors, Contributor, ["cntrb_id"])
    
    # Insert platform data
    if platform_data_list:
        bulk_insert_dicts(logger, platform_data_list, ContributorPlatformData, ["cntrb_id", "platform"])
```

#### B. `get_contributors_by_github_user_id()` - Line 517
**Current**: Queries `gh_user_id` on `Contributor` model
**New**: Join with `ContributorPlatformData` and filter on platform table

```python
def get_contributors_by_github_user_id(session, id):
    return session.query(Contributor).join(
        ContributorPlatformData
    ).filter(
        ContributorPlatformData.gh_user_id == id
    ).all()
```

#### C. Other Query Functions
Search for all functions that query `gh_*` or `gl_*` fields and update them to join with `ContributorPlatformData`.

---

## 4. GitHub Tasks

### A. `/workspaces/augur/augur/tasks/github/pull_requests/core.py`

#### Line 286-324: `process_pull_request_contributors()`
**Current**: Calls `extract_needed_contributor_data()` expecting single dict
**New**: Handle tuple return value

```python
def process_pull_request_contributors(pr: dict, tool_source: str, tool_version: str, data_source: str):
    contributors_core = []
    contributors_platform = []

    # get contributor data and set pr cntrb_id
    core_data, platform_data = extract_needed_contributor_data(pr["user"], tool_source, tool_version, data_source)
    pr["cntrb_id"] = core_data["cntrb_id"]
    contributors_core.append(core_data)
    contributors_platform.append(platform_data)

    # ... similar updates for base, head, assignees, reviewers

    return pr, list(zip(contributors_core, contributors_platform))
```

### B. `/workspaces/augur/augur/tasks/github/pull_requests/tasks.py`

#### Line 185-196: `process_pull_request_review_contributor()`
**Current**: Single dict return
**New**: Tuple return

### C. `/workspaces/augur/augur/tasks/github/issues.py`
#### Line 231-240: Issue contributor processing
Similar updates needed.

### D. `/workspaces/augur/augur/tasks/github/events.py`
#### Line 87-95: `_process_github_event_contributors()`
Similar updates needed.

### E. `/workspaces/augur/augur/tasks/github/messages.py`
#### Line 278: Message contributor processing
Similar updates needed.

---

## 5. Facade GitHub Tasks

### A. `/workspaces/augur/augur/tasks/github/facade_github/tasks.py`

#### Line 54: Access `gh_login`
**Current**: `contributors_with_matching_name[0].gh_login`
**New**: Need to join with platform data or use eager loading

```python
# Option 1: Join query
login_query = session.query(Contributor, ContributorPlatformData.gh_login).join(
    ContributorPlatformData
).filter(
    Contributor.cntrb_full_name == name
).first()

if login_query:
    contributor, gh_login = login_query
    login = gh_login
```

#### Lines 95-120: Building `cntrb` dict
**Current**: Includes `gh_user_id`, `gh_login`, etc. in one dict
**New**: Split into core and platform data

```python
# Core contributor data
cntrb_core = {
    "cntrb_id": cntrb_id.to_UUID(),
    "cntrb_login": user_data['login'],
    "cntrb_created_at": user_data['created_at'],
    "cntrb_email": user_data['email'] if 'email' in user_data else None,
    # ... other core fields
}

# Platform data
cntrb_platform = {
    "cntrb_id": cntrb_id.to_UUID(),
    "platform": "github",
    "gh_user_id": user_data['id'],
    "gh_login": user_data['login'],
    # ... other platform fields
}
```

### B. `/workspaces/augur/augur/tasks/github/facade_github/contributor_interfaceable/contributor_interface.py`

#### Line 164: `get_contributors_by_github_user_id`
Already updated in lib.py section.

#### Line 175: Error message with `gh_user_id`
No change needed - just message text.

#### Line 228: Query with `gh_user_id`
**Current**: `self.contributors_table.c.gh_user_id == cntrb["gh_user_id"]`
**New**: Query should now target platform_data table or join

---

## 6. GitLab Tasks

### `/workspaces/augur/augur/tasks/gitlab/merge_request_task.py`
#### Line 589-605: `process_mr_contributors()`
Update to use tuple return from `extract_needed_gitlab_contributor_data()`

### `/workspaces/augur/augur/tasks/gitlab/issues_task.py`
#### Line 354+: `process_gitlab_issue_comment_contributors()`
Similar updates.

---

## 7. Data Analysis Workers

### `/workspaces/augur/augur/tasks/data_analysis/contributor_breadth_worker/contributor_breadth_worker.py`

**Multiple locations using `gh_login`**:
- Line 35, 40, 46, 52: SQL queries selecting `gh_login`
- Line 67, 70: Query with `c.gh_login`
- Line 81, 84: Accessing `gh_login` from results
- Line 95, 98, 99: Using `gh_login` in API calls

**Action**: Update all SQL queries to join with `contributor_platform_data`:

```sql
SELECT c.cntrb_id, cpd.gh_login, ...
FROM contributors c
LEFT JOIN contributor_platform_data cpd ON c.cntrb_id = cpd.cntrb_id AND cpd.platform = 'github'
WHERE cpd.gh_login IS NOT NULL
```

### `/workspaces/augur/augur/tasks/data_analysis/pull_request_analysis_worker/tasks.py`

#### Line 145: `SELECT cntrb_id, gh_login FROM augur_data.contributors`
**New**: 
```sql
SELECT c.cntrb_id, cpd.gh_login 
FROM augur_data.contributors c
LEFT JOIN augur_data.contributor_platform_data cpd ON c.cntrb_id = cpd.cntrb_id AND cpd.platform = 'github'
```

#### Line 151: Accessing `gh_login` from DataFrame
Should still work after query update.

---

## 8. API Layer

### `/workspaces/augur/augur/api/server.py`

#### Line 517: `ContributorType` GraphQL type
**Current**: May directly expose `gh_*` fields from Contributor model
**New**: Need to add resolvers or eager load platform_data relationship

```python
class ContributorType(SQLAlchemyObjectType):
    class Meta:
        model = Contributor
    
    # Add platform_data field
    platform_data = graphene.List(lambda: ContributorPlatformDataType)
    
    # Add computed fields for backward compatibility
    gh_login = graphene.String()
    gh_user_id = graphene.Int()
    
    def resolve_gh_login(parent, info):
        github_data = next((pd for pd in parent.platform_data if pd.platform == 'github'), None)
        return github_data.gh_login if github_data else None
    
    def resolve_gh_user_id(parent, info):
        github_data = next((pd for pd in parent.platform_data if pd.platform == 'github'), None)
        return github_data.gh_user_id if github_data else None
```

---

## 9. Test Files

### Search Pattern
All test files that mock or assert on contributor data with `gh_*` or `gl_*` fields:
- `tests/test_application/test_*`
- `tests/test_metrics/test_*`
- `tests/test_routes/test_*`
- `tests/test_tasks/test_*`

**Action**: Update test fixtures and assertions to use two-table structure.

---

## 10. Migration Scripts (Legacy)

### `/workspaces/augur/augur/application/schema/alembic/versions/1_augur_new_changes.py`

**Lines 301, 311, 406, 414**: INSERT statements with `gh_*`, `gl_*` fields

**Action**: No change needed - these are historical migrations and should not be modified.

---

## Summary of Changes by Category

| Category | Files Affected | Primary Changes |
|----------|---------------|-----------------|
| **Models** | 1 file | Add new model, update Contributor |
| **Data Parsing** | 1 file | Update 2 functions to return tuples |
| **Database Lib** | 1 file | Update insertion and query functions |
| **GitHub Tasks** | 5 files | Handle tuple returns, update queries |
| **Facade Tasks** | 3 files | Split data, update joins |
| **GitLab Tasks** | 2 files | Handle tuple returns |
| **Data Analysis** | 2 files | Update SQL queries with joins |
| **API** | 1 file | Add resolvers for platform data |
| **Tests** | Multiple | Update fixtures and assertions |

---

## Implementation Order

1. ✅ **Migration Script** (already created)
2. **SQLAlchemy Models** (foundation for all code)
3. **Data Parsing Functions** (affects data flow)
4. **Database Library Functions** (used by all tasks)
5. **GitHub Core Tasks** (high priority)
6. **Facade Tasks** (high priority)
7. **GitLab Tasks**
8. **Data Analysis Workers**
9. **API Layer**
10. **Tests**

---

## Testing Checklist

After each update:
- [ ] Unit tests pass for modified module
- [ ] Integration test: GitHub PR collection workflow
- [ ] Integration test: Git commit (facade) workflow
- [ ] Integration test: GitLab collection workflow
- [ ] API queries return correct data
- [ ] No performance regression in contributor queries
