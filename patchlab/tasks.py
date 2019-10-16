from celery import shared_task


@shared_task
def email_merge_request(merge_request):
    pass


@shared_task
def email_comment(comment):
    pass
