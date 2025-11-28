from django import forms
from .models import CCRSubmission, Course

class CCRSubmissionForm(forms.ModelForm):
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),
        empty_label="Select a course",
        widget=forms.Select(attrs={
            'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
            'id': 'course-select',
            'onchange': 'updateCourseInfo()'
        })
    )
    
    class Meta:
        model = CCRSubmission
        fields = [
            'course', 'course_code_title', 'course_coordinator',
            'q1_topics_included', 'q2_topics_adjustments', 'q3_week_distribution',
            'q4_books_relevance', 'q5_prerequisite_course',
            'clo1_student_centered', 'clo1_measurable', 'clo1_achievable', 'clo1_correct_verb',
            'clo2_student_centered', 'clo2_measurable', 'clo2_achievable', 'clo2_correct_verb',
            'clo3_student_centered', 'clo3_measurable', 'clo3_achievable', 'clo3_correct_verb',
            'clo4_student_centered', 'clo4_measurable', 'clo4_achievable', 'clo4_correct_verb',
            'clo1_domain', 'clo1_level', 'clo1_ga_mapping',
            'clo2_domain', 'clo2_level', 'clo2_ga_mapping',
            'clo3_domain', 'clo3_level', 'clo3_ga_mapping',
            'clo4_domain', 'clo4_level', 'clo4_ga_mapping',
            'group_member_1', 'group_member_2', 'group_member_3', 'group_member_4'
        ]
        widgets = {
            'course_code_title': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50',
                'readonly': 'readonly',
                'id': 'course-code-title'
            }),
            'course_coordinator': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Enter course coordinator name'
            }),
            'q1_topics_included': forms.Textarea(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'rows': 3,
                'placeholder': 'Mention if all HEC topics are included or not...'
            }),
            'q2_topics_adjustments': forms.Textarea(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'rows': 3,
                'placeholder': 'Mention topics to add or remove...'
            }),
            'q3_week_distribution': forms.Textarea(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'rows': 3,
                'placeholder': 'Comment on week-wise distribution...'
            }),
            'q4_books_relevance': forms.Textarea(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'rows': 3,
                'placeholder': 'Comment on textbook and reference books...'
            }),
            'q5_prerequisite_course': forms.Textarea(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'rows': 3,
                'placeholder': 'Comment on prerequisite course...'
            }),
            # CLO Domain fields
            'clo1_domain': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo1_level': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo1_ga_mapping': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo2_domain': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo2_level': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo2_ga_mapping': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo3_domain': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo3_level': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo3_ga_mapping': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo4_domain': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo4_level': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            'clo4_ga_mapping': forms.TextInput(attrs={'class': 'w-full border border-gray-300 rounded px-2 py-1'}),
            # Group members
            'group_member_1': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Name and Signature'
            }),
            'group_member_2': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Name and Signature'
            }),
            'group_member_3': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Name and Signature'
            }),
            'group_member_4': forms.TextInput(attrs={
                'class': 'w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Name and Signature'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.faculty = kwargs.pop('faculty', None)
        super().__init__(*args, **kwargs)
        
        if self.faculty:
            # Only show courses assigned to this faculty
            self.fields['course'].queryset = self.faculty.assigned_courses.all()
