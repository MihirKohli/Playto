from django.core.management.base import BaseCommand
from merchants.models import Merchant, BankAccount, LedgerEntry


SEED_DATA = [
    {
        'name': 'Acme Corp',
        'email': 'acme@example.com',
        'bank_account': {'account_number': '1111222233334444', 'ifsc_code': 'HDFC0001234', 'holder': 'Acme Corp'},
        'credits': [
            (500_000, 'Customer payment – order #1001'),
            (300_000, 'Customer payment – order #1002'),
            (200_000, 'Customer payment – order #1003'),
        ],
    },
    {
        'name': 'TechStart India',
        'email': 'techstart@example.com',
        'bank_account': {'account_number': '5555666677778888', 'ifsc_code': 'ICIC0005678', 'holder': 'TechStart India'},
        'credits': [
            (1_000_000, 'Customer payment – subscription batch A'),
            (750_000,   'Customer payment – subscription batch B'),
        ],
    },
    {
        'name': 'Kirana Plus',
        'email': 'kirana@example.com',
        'bank_account': {'account_number': '9999000011112222', 'ifsc_code': 'SBIN0009012', 'holder': 'Kirana Plus'},
        'credits': [
            (250_000, 'Customer payment – invoice #501'),
            (150_000, 'Customer payment – invoice #502'),
            (100_000, 'Customer payment – invoice #503'),
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed 3 merchants with bank accounts and credit history'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing merchants before seeding')

    def handle(self, *args, **options):
        if options['reset']:
            Merchant.objects.all().delete()
            self.stdout.write('Existing merchants deleted.')

        for data in SEED_DATA:
            merchant, created = Merchant.objects.get_or_create(
                email=data['email'],
                defaults={'name': data['name']},
            )
            if not created:
                self.stdout.write(f'  Skipped (already exists): {data["name"]}')
                continue

            ba = data['bank_account']
            BankAccount.objects.create(
                merchant=merchant,
                account_number=ba['account_number'],
                ifsc_code=ba['ifsc_code'],
                account_holder_name=ba['holder'],
                is_primary=True,
            )

            for amount, description in data['credits']:
                LedgerEntry.objects.create(
                    merchant=merchant,
                    entry_type='CREDIT',
                    amount_paise=amount,
                    status='SETTLED',
                    description=description,
                )

            total_rupees = sum(a for a, _ in data['credits']) // 100
            self.stdout.write(f'  Created: {data["name"]} (balance ₹{total_rupees:,})')

        self.stdout.write(self.style.SUCCESS('Seed complete.'))
