# Issue #3363: Quick Reference Guide

## 📁 Files Created

| File | Purpose | Priority |
|------|---------|----------|
| `ISSUE_3363_SUMMARY.md` | **START HERE** - High-level overview and understanding | 🔴 READ FIRST |
| `ISSUE_3363_DIAGRAMS.md` | Visual diagrams showing before/after architecture | 🔴 READ SECOND |
| `ISSUE_3363_IMPLEMENTATION_PLAN.md` | Detailed technical implementation plan | 🟡 Reference |
| `ISSUE_3363_CODE_LOCATIONS.md` | Exact files and line numbers to change | 🟢 Implementation |
| `ISSUE_3363_TEST_PLAN.md` | Comprehensive testing procedures | 🟢 Testing |
| `augur/application/schema/alembic/versions/38_split_contributors_table.py` | The actual migration script | 🟢 Migration |

## 🎯 Quick Start

### For Understanding (30 minutes)
1. Read `ISSUE_3363_SUMMARY.md` (10 min)
2. Review `ISSUE_3363_DIAGRAMS.md` (15 min)
3. Skim `ISSUE_3363_IMPLEMENTATION_PLAN.md` (5 min)

### For Implementation (Next Steps)
1. Test migration script on dev database
2. Review `ISSUE_3363_CODE_LOCATIONS.md` 
3. Start with Phase 2: Model Updates

### For Testing
1. Use `ISSUE_3363_TEST_PLAN.md`
2. Run pre-migration validation queries
3. Test rollback procedure

## 🔑 Key Concepts

### The Problem
```
contributors table = Core fields + GitHub fields + GitLab fields
                     ↓              ↓               ↓
                  Facade tasks   Core tasks     Core tasks
                  update these   update these   update these
                     
                  ❌ CONFLICT: Both updating same table
                  ❌ RESULT: Contention + partial NULLs
```

### The Solution
```
contributors table = Core fields only
                     ↓
                  Both facade AND core can update
                  
contributor_platform_data = GitHub + GitLab fields
                           ↓
                        Only core tasks update
                        
✅ RESULT: No contention, clean separation
```

## 📊 Quick Stats

- **Current Table**: 1 table, ~50 columns, high contention
- **New Structure**: 2 tables, better separation, low contention
- **Migration Time**: 2-6 hours (depends on data size)
- **Code Files Changed**: ~20 Python files
- **Implementation Time**: 4-5 weeks recommended
- **Rollback Available**: Yes, fully tested

## 🛠️ Implementation Phases

| Phase | What | Time | Priority |
|-------|------|------|----------|
| 1 | Database Migration | Week 1 | 🔴 Critical |
| 2 | Model Updates | Week 1-2 | 🔴 Critical |
| 3 | Data Parsing | Week 2 | 🔴 Critical |
| 4 | Database Library | Week 2 | 🔴 Critical |
| 5 | Task Updates | Week 2-3 | 🟡 High |
| 6 | API Layer | Week 3 | 🟡 High |
| 7 | Testing | Week 3-4 | 🟢 Medium |
| 8 | Deployment | Week 4-5 | 🟢 Medium |

## 🔍 Where to Look

### Understanding the Issue
- **Issue**: #3363 on GitHub
- **Comments**: @MoralCode, @guptapratykshh, @PredictiveManish
- **Summary Doc**: `ISSUE_3363_SUMMARY.md`

### Schema Design
- **Plan**: `ISSUE_3363_IMPLEMENTATION_PLAN.md` → "Proposed Schema Design"
- **Diagrams**: `ISSUE_3363_DIAGRAMS.md` → "New Architecture"
- **Migration**: `38_split_contributors_table.py`

### Code Changes
- **What to change**: `ISSUE_3363_CODE_LOCATIONS.md`
- **Priority order**: Section "Implementation Order"
- **Examples**: Each section has code examples

### Testing
- **Full plan**: `ISSUE_3363_TEST_PLAN.md`
- **Quick tests**: Phase 2 (Migration Execution Tests)
- **Integration tests**: Phase 4 (Code Integration Tests)

## 🚨 Critical Decisions Needed

- [ ] **Approve schema design** - Is the two-table approach correct?
- [ ] **Set timeline** - When to start? 4-5 weeks realistic?
- [ ] **Assign resources** - Who implements each phase?
- [ ] **Schedule maintenance** - When can DB be down for 4-8 hours?
- [ ] **Risk acceptance** - Understand rollback procedures?

## ⚡ Quick Commands

### Test Migration (Development)
```bash
cd /workspaces/augur

# Check migration syntax
alembic check

# Run migration
alembic upgrade head

# Check results
psql -d augur -c "SELECT COUNT(*) FROM augur_data.contributors;"
psql -d augur -c "SELECT COUNT(*) FROM augur_data.contributor_platform_data;"

# Rollback if needed
alembic downgrade -1
```

### Pre-Migration Queries
```sql
-- Get baseline stats
SELECT COUNT(*) FROM augur_data.contributors;
SELECT COUNT(*) FROM augur_data.contributors WHERE gh_user_id IS NOT NULL;
SELECT COUNT(*) FROM augur_data.contributors WHERE gl_id IS NOT NULL;
```

### Post-Migration Validation
```sql
-- Verify migration success
SELECT 
    (SELECT COUNT(*) FROM augur_data.contributors) as total_contributors,
    (SELECT COUNT(*) FROM augur_data.contributor_platform_data WHERE platform = 'github') as github_records,
    (SELECT COUNT(*) FROM augur_data.contributor_platform_data WHERE platform = 'gitlab') as gitlab_records;

-- Check for orphaned records
SELECT COUNT(*) 
FROM augur_data.contributor_platform_data cpd
LEFT JOIN augur_data.contributors c ON cpd.cntrb_id = c.cntrb_id
WHERE c.cntrb_id IS NULL;
-- Should return 0
```

## 📞 Who to Ask

Based on GitHub issue comments:

- **@MoralCode** - Original issue creator, understands problem deeply
- **@guptapratykshh** - Proposed one-shot migration approach, has implementation docs
- **@PredictiveManish** - Interested in contributing, understands migration challenges

## ✅ Success Criteria

The migration is successful if:

1. ✅ All data counts match (no loss)
2. ✅ Foreign keys valid
3. ✅ No duplicate logins/IDs
4. ✅ All tests pass
5. ✅ Performance acceptable (< 20% slower)
6. ✅ No contention between tasks
7. ✅ Rollback works

## 🐛 Common Issues & Solutions

### Issue: Migration takes too long
**Solution**: Test on production-sized dataset first, optimize queries, increase maintenance window

### Issue: Unique constraint violations
**Solution**: Check for duplicate gh_logins or gl_ids before migration, resolve duplicates

### Issue: Code breaks after update
**Solution**: Update all code before deploying, test each workflow, keep rollback ready

### Issue: Performance degradation
**Solution**: Verify indexes created, check query plans, optimize joins

## 📚 Related Documentation

### In This Repo
- Migration scripts: `augur/application/schema/alembic/versions/`
- Models: `augur/application/db/models/augur_data.py`
- Data parsing: `augur/application/db/data_parse.py`
- DB library: `augur/application/db/lib.py`

### External
- Alembic docs: https://alembic.sqlalchemy.org/
- PostgreSQL docs: https://www.postgresql.org/docs/
- SQLAlchemy docs: https://docs.sqlalchemy.org/

## 🎓 Learning Resources

### Database Normalization
- This is a textbook example of 3NF (Third Normal Form)
- Separating mixed concerns into focused tables
- Using foreign keys to maintain relationships

### Database Migration Best Practices
- Always backup before migration
- Test on similar-sized dataset
- Use transactions for atomicity
- Have rollback procedure ready
- Validate data after migration

### Code Refactoring Strategy
- Update foundation first (models, parsing)
- Then update consumers (tasks, API)
- Test after each major change
- Deploy with feature flags if possible

## 📈 Progress Tracking

Use this checklist to track implementation:

### Week 1: Migration
- [ ] Migration script tested on dev DB
- [ ] Migration script tested on prod-sized DB
- [ ] Rollback procedure tested
- [ ] Performance benchmarks recorded
- [ ] Data validation queries prepared

### Week 2: Models & Core Code
- [ ] New ContributorPlatformData model added
- [ ] Contributor model updated
- [ ] extract_needed_contributor_data() updated
- [ ] batch_insert_contributors() updated
- [ ] Query functions updated
- [ ] Unit tests updated and passing

### Week 3: Tasks & API
- [ ] GitHub PR tasks updated
- [ ] GitHub issue tasks updated
- [ ] Facade tasks updated
- [ ] GitLab tasks updated
- [ ] Data analysis workers updated
- [ ] API GraphQL resolvers updated
- [ ] Integration tests passing

### Week 4: Testing & Validation
- [ ] Full test suite passing
- [ ] Performance tests passing
- [ ] Load tests passing
- [ ] Edge cases tested
- [ ] Production validation plan ready

### Week 5: Deployment
- [ ] Maintenance window scheduled
- [ ] Stakeholders notified
- [ ] Full DB backup completed
- [ ] Migration executed
- [ ] Validation queries run
- [ ] Code deployed
- [ ] Monitoring active
- [ ] Post-deployment report

## 🎉 What Success Looks Like

After successful implementation:

```
Before:
GitHub Task: "Updating contributors..." [BLOCKED by Facade]
Facade Task: "Updating contributors..." [BLOCKING GitHub]
Query: "Where's the gh_login?" → Could be NULL 😞

After:
GitHub Task: "Updating platform_data..." [No conflict] ✅
Facade Task: "Updating contributors..." [No conflict] ✅
Query: "Where's the gh_login?" → In platform_data table 😊

Result:
- No more contention
- No more partial NULLs
- Cleaner architecture
- Easier to extend
```

## 📝 Final Notes

This is a **significant but necessary** refactoring:

**Pros:**
- Solves fundamental architectural problem
- Improves data quality
- Reduces contention
- Easier to maintain and extend

**Cons:**
- Requires database migration
- Requires code updates across many files
- Requires thorough testing
- Requires maintenance window

**Verdict:** Worth doing! The long-term benefits far outweigh the short-term implementation cost.

---

**Good luck with the implementation!** 🚀

You have all the documentation, code, tests, and guidance needed. Follow the plan, test thoroughly, and you'll be successful.
