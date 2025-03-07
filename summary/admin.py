from django.contrib import admin

from summary.models import UserCourseSummary, CourseDailyStats, UserPointsSummary, UserCourseDailySummary

from helpers.mixins.PermissionMixins import ReadOnlyAdminMixin


STR_UPDATE_SUMMARY = "Update summary"

def message_user(model, request, model_name, query_count):
    if query_count == 1:
        model.message_user(request,
                           model_name + " summary successfully updated.")
    elif query_count > 0:
        model.message_user(request,
                           model_name + " summaries successfully updated.")


class UserCourseSummaryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('user',
                    'course',
                    'points',
                    'total_downloads',
                    'total_activity',
                    'quizzes_passed',
                    'badges_achieved',
                    'pretest_score',
                    'media_viewed',
                    'completed_activities')
    actions = ['update_summary']

    def update_summary(self, request, queryset):
        for course_summary in queryset:
            course_summary.update_summary()
        message_user(self, request, "User-course", queryset.count())

    update_summary.short_description = STR_UPDATE_SUMMARY


class CourseDailyStatsAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('course', 'day', 'type', 'total')
    date_hierarchy = 'day'
    ordering = '-day',
    actions = ['update_summary']

    def update_summary(self, request, queryset):
        for daily_stats in queryset:
            CourseDailyStats.update_daily_summary(daily_stats.course.id,
                                                  daily_stats.day)
        message_user(self, request, "Daily stats", queryset.count())

    update_summary.short_description = STR_UPDATE_SUMMARY


class UserPointsSummaryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'points', 'badges')
    ordering = '-points',
    actions = ['update_summary']

    def update_summary(self, request, queryset):
        for user_points in queryset:
            user_points.update_points()
        message_user(self, request, "User points", queryset.count())

    update_summary.short_description = STR_UPDATE_SUMMARY


class UserCourseDailySummaryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('day',
                    'user',
                    'course',
                    'type',
                    'total_tracked',
                    'time_spent_tracked',
                    'total_submitted',
                    'time_spent_submitted')
    ordering = ['-day']


admin.site.register(UserCourseSummary, UserCourseSummaryAdmin)
admin.site.register(CourseDailyStats, CourseDailyStatsAdmin)
admin.site.register(UserPointsSummary, UserPointsSummaryAdmin)
admin.site.register(UserCourseDailySummary, UserCourseDailySummaryAdmin)
