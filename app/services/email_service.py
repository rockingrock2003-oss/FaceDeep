import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings


class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME

    def _get_connection(self) -> smtplib.SMTP:
        server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        server.starttls()
        server.login(self.smtp_user, self.smtp_password)
        return server

    def send_verification_email(self, to_email: str, username: str, token: str):
        verify_link = f"{settings.BASE_URL}/api/v1/auth/verify-email?token={token}"

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #4CAF50; color: white; padding: 20px; text-align: center;">
                <h1>FaceDeep - Email Verification</h1>
            </div>
            <div style="padding: 20px; border: 1px solid #ddd;">
                <p>Hello <strong>{username}</strong>,</p>
                <p>Thank you for registering with FaceDeep. Please verify your email address by clicking the button below:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verify_link}"
                       style="background-color: #4CAF50; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; font-size: 16px;">
                        Verify Email
                    </a>
                </div>
                <p>Or copy this link:</p>
                <p style="word-break: break-all; color: #4CAF50;">{verify_link}</p>
                <p style="color: #999; font-size: 12px;">This link expires in 24 hours.</p>
                <p style="color: #999; font-size: 12px;">If you did not register, ignore this email.</p>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "FaceDeep - Verify Your Email"
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        server = self._get_connection()
        try:
            server.sendmail(self.from_email, to_email, msg.as_string())
        finally:
            server.quit()


email_service = EmailService()
