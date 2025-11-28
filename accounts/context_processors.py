# In context_processors.py - Add dynamic form status
from .models import CCRForm, DynamicForm

def ccr_form_status(request):
    """
    Context processor to add form_active status to all templates
    """
    def check_ccr_form_status():
        try:
            ccr_form_obj = CCRForm.objects.filter(name="CCR Form").first()
            if ccr_form_obj and ccr_form_obj.status == CCRForm.STATUS_ACTIVE:
                return True
            return False
        except Exception:
            return False
    
    def check_dynamic_form_status():
        """
        Check if dynamic forms are active
        """
        try:
            dynamic_form = DynamicForm.objects.filter(status=DynamicForm.STATUS_ACTIVE).first()
            if dynamic_form:
                return True
            return False
        except Exception:
            return False
    
    return {
        'form_active': check_ccr_form_status(),
        'dynamic_form_active': check_dynamic_form_status()
    }