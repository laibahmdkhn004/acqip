from .models import CCRForm

def ccr_form_status(request):
    """
    Context processor to add form_active status to all templates
    """
    def check_ccr_form_status():
        """
        Check if CCR forms are active
        """
        try:
            ccr_form_obj = CCRForm.objects.filter(name="CCR Form").first()
            if ccr_form_obj and ccr_form_obj.status == CCRForm.STATUS_ACTIVE:
                return True
            return False
        except Exception:
            return False
    
    return {
        'form_active': check_ccr_form_status()
    }