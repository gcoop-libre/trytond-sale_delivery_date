# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond import backend
from trytond.pool import Pool, PoolMeta
from trytond.model import fields
from trytond.pyson import Eval, Bool, If
from trytond.transaction import Transaction

__all__ = ['Sale', 'SaleLine']


class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'

    @classmethod
    def process(cls, sales):
        pool = Pool()
        SaleLine = pool.get('sale.line')
        to_write = []
        for sale in sales:
            for line in sale.lines:
                if (line.type == 'line' and line.product
                        and not line.manual_delivery_date):
                    date = line.on_change_with_shipping_date(
                        name='shipping_date')
                    to_write.extend(([line], {
                                'manual_delivery_date': date,
                                }))
        if to_write:
            SaleLine.write(*to_write)
        super(Sale, cls).process(sales)

    def _group_shipment_key(self, moves, move):
        # Group shipments by move planned_date, so one shipment is created
        # for each planned_date
        grouping = super(Sale, self)._group_shipment_key(moves, move)
        new_grouping = [('planned_date', move[1].planned_date)]
        for field, value in grouping:
            if field == 'planned_date':
                continue
            new_grouping.append((field, value))
        return tuple(new_grouping)


class SaleLine(metaclass=PoolMeta):
    __name__ = 'sale.line'
    manual_delivery_date = fields.Date('Delivery Date',
            states={
                'invisible': ((Eval('type') != 'line')
                    | (If(Bool(Eval('quantity')), Eval('quantity', 0), 0)
                        <= 0)),
                },
            depends=['type', 'quantity'])

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        cls.shipping_date.states['invisible'] = True

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        sql_table = cls.__table__()

        # Migration from 3.2
        table = backend.TableHandler(cls, module_name)
        move_delivery_dates = (not table.column_exist('manual_delivery_date')
            and table.column_exist('shipping_date'))

        super(SaleLine, cls).__register__(module_name)

        if move_delivery_dates:
            cursor.execute(*sql_table.update(
                    columns=[sql_table.manual_delivery_date],
                    values=[sql_table.shipping_date]))
            table.drop_column('shipping_date')

    @fields.depends('manual_delivery_date',
        methods=['on_change_with_shipping_date'])
    def on_change_with_manual_delivery_date(self):
        if self.manual_delivery_date:
            return self.manual_delivery_date
        return super(SaleLine,
            self).on_change_with_shipping_date(name='shipping_date')

    @fields.depends('manual_delivery_date')
    def on_change_with_shipping_date(self, name=None):
        return self.manual_delivery_date or super(SaleLine,
            self).on_change_with_shipping_date(name=name)

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default.setdefault('manual_delivery_date')
        return super(SaleLine, cls).copy(lines, default)

    @property
    @fields.depends('manual_delivery_date')
    def planned_shipping_date(self):
        if self.manual_delivery_date:
            return self.manual_delivery_date
        return super().planned_shipping_date
